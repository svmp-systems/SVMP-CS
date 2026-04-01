"""Workflow B: process ready sessions and decide answer vs escalation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from svmp_core.config import Settings, get_settings, get_tenant_confidence_threshold
from svmp_core.core import (
    EscalationTarget,
    IdentityFrame,
    build_answered_log,
    build_escalated_log,
    choose_domain,
    evaluate_similarity,
    request_escalation,
)
from svmp_core.db.base import Database
from svmp_core.exceptions import DatabaseError, RoutingError
from svmp_core.integrations import generate_completion, get_whatsapp_provider
from svmp_core.models import (
    GovernanceDecision,
    KnowledgeEntry,
    OutboundSendResult,
    OutboundTextMessage,
    SessionState,
)


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TypingIndicatorAttempt:
    """Resolved typing-indicator target information for one processing run."""

    provider_name: str
    inbound_message_id: str | None


def _strip_json_fence(value: str) -> str:
    """Remove markdown code fences around JSON responses when present."""

    normalized = value.strip()
    if normalized.startswith("```") and normalized.endswith("```"):
        lines = normalized.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return normalized


@dataclass(frozen=True)
class MatcherResult:
    """Normalized OpenAI match result."""

    matcher: str
    entry: KnowledgeEntry | None
    score: float | None
    reason: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ConversationView:
    """Derived active-question and archived context inputs."""

    active_messages: list[str]
    active_question: str
    context: str


def _build_conversation_view(session: SessionState) -> ConversationView:
    """Build the active question from current-window messages and archived context."""

    active_messages = [message.text.strip() for message in session.messages if message.text.strip()]
    active_question = " ".join(active_messages).strip()
    context = " ".join(
        item.strip()
        for item in session.context
        if isinstance(item, str) and item.strip()
    ).strip()
    return ConversationView(
        active_messages=active_messages,
        active_question=active_question,
        context=context,
    )


def _normalize_similarity_score(raw_score: Any) -> float:
    """Normalize matcher scores from either 0-1 or 0-100 into 0-1."""

    if not isinstance(raw_score, (int, float)):
        raise RoutingError("OpenAI matcher returned an invalid similarity score")

    score = float(raw_score)
    if 0 <= score <= 1:
        return score
    if 1 < score <= 100:
        return score / 100.0
    raise RoutingError("OpenAI matcher returned an invalid similarity score")


async def _openai_match(
    conversation: ConversationView,
    entries: list[KnowledgeEntry],
    *,
    settings: Settings,
) -> MatcherResult:
    """Use OpenAI directly to choose the best FAQ candidate."""

    if not entries:
        return MatcherResult(
            matcher="openai",
            entry=None,
            score=None,
            reason="no candidate match available",
            metadata={"candidatesConsidered": 0},
        )

    candidates = list(entries)
    candidate_payload = [
        {
            "index": index,
            "question": entry.question,
            "answer": entry.answer,
            "tags": list(entry.tags),
        }
        for index, entry in enumerate(candidates)
    ]

    response = await generate_completion(
        system_prompt=(
            "You rank FAQ candidates for customer-support automation. "
            "activeQuestion is the only text that should drive candidate selection and answer decision making. "
            "context is archived history from previous processed windows and must never override activeQuestion. "
            "Use context only to clarify references when activeQuestion clearly points back to earlier history. "
            "If activeQuestion alone is unclear or not safely answerable from the candidates, return no match. "
            "Return valid JSON only with keys bestIndex, similarityScore, and reason. "
            "bestIndex must be an integer index from the candidates list or null if none match. "
            "similarityScore must be a number between 0 and 1, or between 0 and 100, or null when there is no safe match."
        ),
        user_prompt=json.dumps(
            {
                "activeQuestion": conversation.active_question,
                "activeMessages": conversation.active_messages,
                "context": conversation.context,
                "coreRule": "Use activeQuestion as the authoritative ask. activeMessages are the raw current debounce-window texts. context is previous processed history only and must not override activeQuestion.",
                "candidates": candidate_payload,
            },
            ensure_ascii=True,
        ),
        settings=settings,
        temperature=0.0,
        max_tokens=200,
    )
    parsed = json.loads(_strip_json_fence(response))

    best_index = parsed.get("bestIndex")
    similarity_score = parsed.get("similarityScore")
    reason = str(parsed.get("reason", "selected by OpenAI matcher")).strip() or "selected by OpenAI matcher"

    if best_index is None:
        return MatcherResult(
            matcher="openai",
            entry=None,
            score=None,
            reason=reason,
            metadata={"candidatesConsidered": len(candidate_payload)},
        )

    if not isinstance(best_index, int) or best_index < 0 or best_index >= len(candidates):
        raise RoutingError("OpenAI matcher returned an invalid candidate index")

    matched_entry = candidates[best_index]
    return MatcherResult(
        matcher="openai",
        entry=matched_entry,
        score=_normalize_similarity_score(similarity_score),
        reason=reason,
        metadata={"candidatesConsidered": len(candidate_payload)},
    )


def _matcher_metadata(result: MatcherResult) -> dict[str, Any]:
    """Build governance metadata describing the active matcher result."""

    return {
        "matcherUsed": result.matcher,
        "matcherReason": result.reason,
        **result.metadata,
    }


def _audit_metadata(
    *,
    identity: IdentityFrame,
    session: SessionState,
    decision: str,
    latency_ms: int,
    reason: str,
    provider_name: str | None,
    threshold: float | None,
    similarity_score: float | None,
    similarity_outcome: str,
    candidate_found: bool,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build consistent governance metadata for Workflow B decisions."""

    metadata: dict[str, Any] = {
        "workflow": "workflow_b",
        "decision": decision,
        "decisionReason": reason,
        "latencyMs": latency_ms,
        "sessionId": session.id,
        "provider": provider_name,
        "identity": {
            "tenantId": identity.tenant_id,
            "clientId": identity.client_id,
            "userId": identity.user_id,
        },
        "similarity": {
            "score": similarity_score,
            "threshold": threshold,
            "outcome": similarity_outcome,
            "candidateFound": candidate_found,
        },
    }
    if extra:
        metadata.update(dict(extra))
    return metadata


async def _archive_processed_window(
    database: Database,
    session: SessionState,
    *,
    active_question: str,
    now: datetime,
) -> SessionState:
    """Archive the processed active window while preserving any newer inbound messages."""

    if session.id is None:
        raise DatabaseError("ready session missing id")

    latest_session = await database.session_state.get_by_identity(
        session.tenant_id,
        session.client_id,
        session.user_id,
    )
    if latest_session is None or latest_session.id != session.id:
        raise DatabaseError("failed to load session for archive merge")

    next_context = list(latest_session.context)
    if active_question.strip():
        next_context.append(active_question.strip())

    processed_texts = [message.text.strip() for message in session.messages if message.text.strip()]
    latest_texts = [message.text.strip() for message in latest_session.messages if message.text.strip()]
    remaining_messages = list(latest_session.messages)

    if processed_texts and latest_texts[: len(processed_texts)] == processed_texts:
        remaining_messages = latest_session.messages[len(processed_texts) :]

    has_unprocessed_messages = any(message.text.strip() for message in remaining_messages)

    updated_session = await database.session_state.update_by_id(
        session.id,
        {
            "context": next_context,
            "messages": remaining_messages,
            "updated_at": latest_session.updated_at if has_unprocessed_messages else now,
            "debounce_expires_at": latest_session.debounce_expires_at,
            "processing": False if has_unprocessed_messages else True,
        },
    )
    if updated_session is None:
        raise DatabaseError("failed to archive processed session window")
    return updated_session


def _fallback_domain_id(tenant_document: Mapping[str, Any] | None) -> str | None:
    """Choose a safe fallback domain if tenant domains exist."""

    if not isinstance(tenant_document, Mapping):
        return None

    raw_domains = tenant_document.get("domains", [])
    if not isinstance(raw_domains, list):
        return None

    for domain in raw_domains:
        if isinstance(domain, Mapping):
            domain_id = domain.get("domainId")
            if isinstance(domain_id, str) and domain_id.strip():
                return domain_id.strip()

    return None


async def _send_answer_reply(
    identity: IdentityFrame,
    answer_text: str,
    *,
    provider_name: str | None,
    settings: Settings,
) -> OutboundSendResult:
    """Send an answered response back through the active WhatsApp provider."""

    provider = get_whatsapp_provider(
        settings=settings,
        requested_provider=provider_name or settings.WHATSAPP_PROVIDER,
    )
    return await provider.send_text(
        OutboundTextMessage(
            tenantId=identity.tenant_id,
            clientId=identity.client_id,
            userId=identity.user_id,
            text=answer_text,
            provider=provider.name,
        ),
        settings=settings,
    )


async def _send_typing_indicator(
    attempt: TypingIndicatorAttempt,
    *,
    settings: Settings,
) -> None:
    """Send a provider-native typing indicator when supported."""

    provider = get_whatsapp_provider(
        settings=settings,
        requested_provider=attempt.provider_name,
    )
    await provider.send_typing_indicator(
        inbound_message_id=attempt.inbound_message_id,
        settings=settings,
    )


def _prepare_typing_indicator_attempt(
    session: SessionState,
    *,
    settings: Settings,
) -> TypingIndicatorAttempt:
    """Resolve the provider and latest inbound message id for typing UX."""

    inbound_message_id = None
    for message in reversed(session.messages):
        if message.external_message_id is not None and message.external_message_id.strip():
            inbound_message_id = message.external_message_id.strip()
            break

    return TypingIndicatorAttempt(
        provider_name=session.provider or settings.WHATSAPP_PROVIDER,
        inbound_message_id=inbound_message_id,
    )


def _typing_metadata_base(attempt: TypingIndicatorAttempt) -> dict[str, Any]:
    """Return base audit metadata for a typing-indicator attempt."""

    attempted = attempt.inbound_message_id is not None
    return {
        "typingIndicatorAttempted": attempted,
        "typingIndicatorProvider": attempt.provider_name,
        "typingIndicatorMessageId": attempt.inbound_message_id,
    }


async def _send_typing_indicator_safely(
    attempt: TypingIndicatorAttempt,
    *,
    settings: Settings,
) -> dict[str, Any]:
    """Send typing indicator without letting provider failures affect the workflow."""

    base_metadata = _typing_metadata_base(attempt)
    if not base_metadata["typingIndicatorAttempted"]:
        return {
            **base_metadata,
            "typingIndicatorSent": False,
            "typingIndicatorStatus": "skipped",
            "typingIndicatorError": None,
        }

    try:
        await _send_typing_indicator(attempt, settings=settings)
    except Exception as exc:
        return {
            **base_metadata,
            "typingIndicatorSent": False,
            "typingIndicatorStatus": "error",
            "typingIndicatorError": str(exc),
        }

    return {
        **base_metadata,
        "typingIndicatorSent": True,
        "typingIndicatorStatus": "sent",
        "typingIndicatorError": None,
    }


async def _collect_typing_indicator_metadata(
    task: asyncio.Task[dict[str, Any]],
    attempt: TypingIndicatorAttempt,
) -> dict[str, Any]:
    """Collect typing audit data without blocking the main workflow for long."""

    done, _ = await asyncio.wait({task}, timeout=0.25)
    if task in done:
        return task.result()

    return {
        **_typing_metadata_base(attempt),
        "typingIndicatorSent": False,
        "typingIndicatorStatus": "pending",
        "typingIndicatorError": None,
    }


@dataclass(frozen=True)
class WorkflowBResult:
    """Summary of a Workflow B processing run."""

    processed: bool
    session_id: str | None
    decision: GovernanceDecision | None
    combined_text: str | None
    domain_id: str | None
    similarity_score: float | None
    answer_supplied: str | None
    outbound_send_result: OutboundSendResult | None
    escalation_target: EscalationTarget | None
    reason: str | None
    matcher_used: str | None


async def run_workflow_b(
    database: Database,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
    session_id: str | None = None,
) -> WorkflowBResult:
    """Process one ready session and choose answer vs escalation."""

    runtime_settings = settings or get_settings()
    current_time = now or _utcnow()
    started_at = perf_counter()
    acquired_session: SessionState | None = None

    try:
        if session_id is None:
            acquired_session = await database.session_state.acquire_ready_session(current_time)
        else:
            acquired_session = await database.session_state.acquire_ready_session_by_id(session_id, current_time)
        if acquired_session is None:
            return WorkflowBResult(
                processed=False,
                session_id=None,
                decision=None,
                combined_text=None,
                domain_id=None,
                similarity_score=None,
                answer_supplied=None,
                outbound_send_result=None,
                escalation_target=None,
                reason=None,
                matcher_used=None,
            )

        if acquired_session.id is None:
            raise DatabaseError("ready session missing id")

        identity = IdentityFrame(
            tenant_id=acquired_session.tenant_id,
            client_id=acquired_session.client_id,
            user_id=acquired_session.user_id,
        )
        typing_attempt = _prepare_typing_indicator_attempt(acquired_session, settings=runtime_settings)
        typing_task = asyncio.create_task(
            _send_typing_indicator_safely(typing_attempt, settings=runtime_settings)
        )
        conversation = _build_conversation_view(acquired_session)
        active_question = conversation.active_question
        if not active_question:
            raise RoutingError("ready session has no searchable text")
        combined_text = active_question

        tenant_document = await database.tenants.get_by_tenant_id(acquired_session.tenant_id)
        raw_domains = tenant_document.get("domains", []) if isinstance(tenant_document, Mapping) else []
        fallback_domain_id = _fallback_domain_id(tenant_document)

        try:
            threshold = get_tenant_confidence_threshold(tenant_document)
        except ValueError:
            threshold = runtime_settings.SIMILARITY_THRESHOLD

        try:
            domain_id = choose_domain(
                active_question,
                raw_domains if isinstance(raw_domains, list) else [],
                fallback_domain_id=fallback_domain_id,
            )
        except RoutingError:
            domain_id = fallback_domain_id

        if domain_id is None:
            escalation = request_escalation(
                identity,
                combined_text,
                reason="domain_unresolved",
            )
            typing_metadata = await _collect_typing_indicator_metadata(typing_task, typing_attempt)
            log = build_escalated_log(
                identity,
                combined_text,
                metadata=_audit_metadata(
                    identity=identity,
                    session=acquired_session,
                    decision=GovernanceDecision.ESCALATED.value,
                    latency_ms=int((perf_counter() - started_at) * 1000),
                    reason=escalation.reason,
                    provider_name=acquired_session.provider,
                    threshold=threshold,
                    similarity_score=None,
                    similarity_outcome="not_evaluated",
                    candidate_found=False,
                    extra={
                        "target": escalation.target.value,
                        "reason": "domain_unresolved",
                        "activeQuestion": conversation.active_question,
                        "activeMessages": conversation.active_messages,
                        "context": conversation.context,
                        **typing_metadata,
                    },
                ),
                timestamp=current_time,
            )
            await database.governance_logs.create(log)
            await _archive_processed_window(
                database,
                acquired_session,
                active_question=conversation.active_question,
                now=current_time,
            )
            return WorkflowBResult(
                processed=True,
                session_id=acquired_session.id,
                decision=GovernanceDecision.ESCALATED,
                combined_text=combined_text,
                domain_id=None,
                similarity_score=None,
                answer_supplied=None,
                outbound_send_result=None,
                escalation_target=escalation.target,
                reason=escalation.reason,
                matcher_used="domain_gate",
            )

        entries = await database.knowledge_base.list_active_by_tenant_and_domain(
            acquired_session.tenant_id,
            domain_id,
        )
        openai_match = await _openai_match(
            conversation,
            entries,
            settings=runtime_settings,
        )
        similarity_decision = evaluate_similarity(
            openai_match.score,
            threshold,
            candidate_found=openai_match.entry is not None,
        )
        matcher_metadata = _matcher_metadata(openai_match)

        if similarity_decision.should_answer and openai_match.entry is not None:
            matched_entry = openai_match.entry
            send_result = await _send_answer_reply(
                identity,
                matched_entry.answer,
                provider_name=acquired_session.provider,
                settings=runtime_settings,
            )
            typing_metadata = await _collect_typing_indicator_metadata(typing_task, typing_attempt)
            log = build_answered_log(
                identity,
                combined_text,
                similarity_score=similarity_decision.score or 0.0,
                answer_supplied=matched_entry.answer,
                metadata=_audit_metadata(
                    identity=identity,
                    session=acquired_session,
                    decision=GovernanceDecision.ANSWERED.value,
                    latency_ms=int((perf_counter() - started_at) * 1000),
                    reason=similarity_decision.reason,
                    provider_name=acquired_session.provider,
                    threshold=threshold,
                    similarity_score=similarity_decision.score,
                    similarity_outcome=similarity_decision.outcome.value,
                    candidate_found=True,
                    extra={
                        "domainId": domain_id,
                        "activeQuestion": conversation.active_question,
                        "activeMessages": conversation.active_messages,
                        "context": conversation.context,
                        **typing_metadata,
                        **matcher_metadata,
                        "delivery": {
                            "provider": send_result.provider,
                            "status": send_result.status,
                            "externalMessageId": send_result.external_message_id,
                        },
                    },
                ),
                timestamp=current_time,
            )
            await database.governance_logs.create(log)
            await _archive_processed_window(
                database,
                acquired_session,
                active_question=conversation.active_question,
                now=current_time,
            )
            return WorkflowBResult(
                processed=True,
                session_id=acquired_session.id,
                decision=GovernanceDecision.ANSWERED,
                combined_text=combined_text,
                domain_id=domain_id,
                similarity_score=similarity_decision.score,
                answer_supplied=matched_entry.answer,
                outbound_send_result=send_result,
                escalation_target=None,
                reason=similarity_decision.reason,
                matcher_used="openai",
            )

        escalation = request_escalation(
            identity,
            combined_text,
            reason=similarity_decision.reason,
            metadata={"domainId": domain_id},
        )
        typing_metadata = await _collect_typing_indicator_metadata(typing_task, typing_attempt)
        log = build_escalated_log(
            identity,
            combined_text,
            similarity_score=similarity_decision.score,
            metadata=_audit_metadata(
                identity=identity,
                session=acquired_session,
                decision=GovernanceDecision.ESCALATED.value,
                latency_ms=int((perf_counter() - started_at) * 1000),
                reason=similarity_decision.reason,
                provider_name=acquired_session.provider,
                threshold=threshold,
                similarity_score=similarity_decision.score,
                similarity_outcome=similarity_decision.outcome.value,
                candidate_found=openai_match.entry is not None,
                extra={
                    "domainId": domain_id,
                    "activeQuestion": conversation.active_question,
                    "activeMessages": conversation.active_messages,
                    "context": conversation.context,
                    "reason": similarity_decision.reason,
                    "target": escalation.target.value,
                    **typing_metadata,
                    **matcher_metadata,
                },
            ),
            timestamp=current_time,
        )
        await database.governance_logs.create(log)
        await _archive_processed_window(
            database,
            acquired_session,
            active_question=conversation.active_question,
            now=current_time,
        )
        return WorkflowBResult(
            processed=True,
            session_id=acquired_session.id,
            decision=GovernanceDecision.ESCALATED,
            combined_text=combined_text,
            domain_id=domain_id,
            similarity_score=similarity_decision.score,
            answer_supplied=None,
            outbound_send_result=None,
            escalation_target=escalation.target,
            reason=escalation.reason,
            matcher_used="openai",
        )
    except Exception as exc:
        raise DatabaseError("workflow b processing failed") from exc
