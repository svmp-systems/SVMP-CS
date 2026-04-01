"""Workflow B: process ready sessions and decide answer vs escalation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
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


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def _tokenize(value: str) -> set[str]:
    """Split free text into lowercase searchable tokens."""

    return set(_TOKEN_PATTERN.findall(value.lower()))


def _combine_messages(session: SessionState) -> str:
    """Collapse buffered message fragments into one processing string."""

    return " ".join(message.text.strip() for message in session.messages if message.text.strip()).strip()


@dataclass(frozen=True)
class ConversationView:
    """Derived conversation inputs for matching and routing."""

    combined_text: str
    recent_messages: list[str]
    context: str
    recent_text: str


def _build_conversation_view(session: SessionState) -> ConversationView:
    """Build matcher inputs from archived context plus the active debounce window."""

    messages = [message.text.strip() for message in session.messages if message.text.strip()]
    combined_text = " ".join(messages).strip()
    recent_messages = list(messages)
    recent_text = " ".join(recent_messages).strip()
    context_text = " ".join(
        segment.strip()
        for segment in session.context
        if isinstance(segment, str) and segment.strip()
    ).strip()

    return ConversationView(
        combined_text=combined_text,
        recent_messages=recent_messages,
        context=context_text,
        recent_text=recent_text,
    )


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
            "The core system sends recentMessages as the full current debounce window and context as older history only. do NOT use context for the actual answer, use it only to provide session background. "
            "recentMessages contains only the customer messages collected in the current debounce window before this run. "
            "context contains text from previous processed windows and is supporting context only. "
            "Infer the LAST COHERENT SENTENCE or question from recentMessages and USE ONLY LAST COHERENT SENTENCE as the authoritative ask. "
            "Never let context override the last coherent sentence from recentMessages. "
            "If that final coherent ask is unclear, unrelated to the candidates, or not safely answerable, return no match. "
            "Return valid JSON only with keys bestIndex, similarityScore, and reason. "
            "bestIndex must be an integer index from the candidates list or null if none match. "
            "similarityScore must be either a decimal between 0 and 1 or a percentage-style number between 0 and 100, "
            "or null when there is no safe match."
            "MAKE ABSOLUTE CERTAIN YOU ARE USING THE LAST MEANINGFUL SENTENCE OR QUESTION AS THE ACTUAL QUESTION FROM THE USER."
        ),
        user_prompt=json.dumps(
            {
                "recentMessages": conversation.recent_messages,
                "context": conversation.context,
                "recentText": conversation.recent_text,
                "combinedText": conversation.combined_text,
                "coreRule": "Use the last coherent sentence or question from recentMessages as the authoritative ask. recentMessages is the current debounce window only. context is previous processed history only and must not override it.",
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

    normalized_score = _normalize_similarity_score(similarity_score)

    matched_entry = candidates[best_index]
    return MatcherResult(
        matcher="openai",
        entry=matched_entry,
        score=normalized_score,
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


async def _archive_processed_window(
    database: Database,
    session: SessionState,
    *,
    combined_text: str,
    now: datetime,
) -> SessionState:
    """Move the processed active window into archived context and clear active messages."""

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
    normalized_combined = combined_text.strip()
    if normalized_combined:
        next_context.append(normalized_combined)

    processed_texts = [message.text.strip() for message in session.messages if message.text.strip()]
    remaining_messages = list(latest_session.messages)
    latest_texts = [message.text.strip() for message in latest_session.messages if message.text.strip()]

    if processed_texts and len(latest_texts) >= len(processed_texts):
        processed_prefix = latest_texts[: len(processed_texts)]
        if processed_prefix == processed_texts:
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
    session: SessionState,
    *,
    settings: Settings,
) -> None:
    """Send a provider-native typing indicator when supported."""

    provider = get_whatsapp_provider(
        settings=settings,
        requested_provider=session.provider or settings.WHATSAPP_PROVIDER,
    )
    inbound_message_id = None
    for message in reversed(session.messages):
        if message.external_message_id is not None and message.external_message_id.strip():
            inbound_message_id = message.external_message_id.strip()
            break
    await provider.send_typing_indicator(
        inbound_message_id=inbound_message_id,
        settings=settings,
    )


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
) -> WorkflowBResult:
    """Process one ready session and choose answer vs escalation."""

    runtime_settings = settings or get_settings()
    current_time = now or _utcnow()
    acquired_session: SessionState | None = None

    try:
        acquired_session = await database.session_state.acquire_ready_session(current_time)
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
        try:
            await _send_typing_indicator(acquired_session, settings=runtime_settings)
        except Exception:
            pass
        conversation = _build_conversation_view(acquired_session)
        combined_text = conversation.combined_text
        if not combined_text:
            raise RoutingError("ready session has no searchable text")
        active_query = conversation.recent_text or combined_text

        tenant_document = await database.tenants.get_by_tenant_id(acquired_session.tenant_id)
        raw_domains = tenant_document.get("domains", []) if isinstance(tenant_document, Mapping) else []
        fallback_domain_id = _fallback_domain_id(tenant_document)

        try:
            threshold = get_tenant_confidence_threshold(tenant_document)
        except ValueError:
            threshold = runtime_settings.SIMILARITY_THRESHOLD

        try:
            domain_id = choose_domain(
                active_query,
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
            log = build_escalated_log(
                identity,
                combined_text,
                metadata={
                    "reason": "domain_unresolved",
                    "target": escalation.target.value,
                    "recentMessages": conversation.recent_messages,
                    "recentText": conversation.recent_text,
                    "context": conversation.context,
                },
                timestamp=current_time,
            )
            await database.governance_logs.create(log)
            await _archive_processed_window(
                database,
                acquired_session,
                combined_text=combined_text,
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
            assert matched_entry is not None
            assert acquired_session is not None
            send_result = await _send_answer_reply(
                identity,
                openai_match.entry.answer,
                provider_name=acquired_session.provider,
                settings=runtime_settings,
            )
            log = build_answered_log(
                identity,
                combined_text,
                similarity_score=similarity_decision.score or 0.0,
                answer_supplied=matched_entry.answer,
                metadata={
                    "domainId": domain_id,
                    "recentMessages": conversation.recent_messages,
                    "recentText": conversation.recent_text,
                    "context": conversation.context,
                    **matcher_metadata,
                    "delivery": {
                        "provider": send_result.provider,
                        "status": send_result.status,
                        "externalMessageId": send_result.external_message_id,
                    },
                },
                timestamp=current_time,
            )
            await database.governance_logs.create(log)
            await _archive_processed_window(
                database,
                acquired_session,
                combined_text=combined_text,
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
        log = build_escalated_log(
            identity,
            combined_text,
            similarity_score=similarity_decision.score,
            metadata={
                "domainId": domain_id,
                "recentMessages": conversation.recent_messages,
                "recentText": conversation.recent_text,
                "context": conversation.context,
                "reason": similarity_decision.reason,
                "target": escalation.target.value,
                **matcher_metadata,
            },
            timestamp=current_time,
        )
        await database.governance_logs.create(log)
        await _archive_processed_window(
            database,
            acquired_session,
            combined_text=combined_text,
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
