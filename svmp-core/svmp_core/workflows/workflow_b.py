"""Workflow B: process ready sessions and decide answer vs escalation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
from svmp_core.core.timing import LatencyTrace
from svmp_core.db.base import Database
from svmp_core.exceptions import DatabaseError, RoutingError
from svmp_core.integrations import generate_completion, get_whatsapp_provider
from svmp_core.logger import get_logger
from svmp_core.models import (
    GovernanceDecision,
    KnowledgeEntry,
    OutboundSendResult,
    OutboundTextMessage,
    SessionState,
)

logger = get_logger("svmp.workflows.workflow_b")


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


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


def _duration_ms_between(start: datetime | None, end: datetime | None) -> int | None:
    """Return the integer duration in milliseconds between two timestamps."""

    if start is None or end is None:
        return None
    normalized_start = _normalize_utc_datetime(start)
    normalized_end = _normalize_utc_datetime(end)
    return int(round((normalized_end - normalized_start).total_seconds() * 1000))


def _normalize_utc_datetime(value: datetime) -> datetime:
    """Normalize datetimes to timezone-aware UTC for safe arithmetic."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_trace_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO timestamp emitted by the latency tracer."""

    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _parse_optional_datetime(value: Any) -> datetime | None:
    """Parse either datetime or ISO-string values into UTC-aware datetimes."""

    if isinstance(value, datetime):
        return _normalize_utc_datetime(value)
    if isinstance(value, str) and value.strip():
        return _parse_trace_timestamp(value)
    return None


def _message_window_timing(
    session: SessionState,
    *,
    workflow_started_at: datetime,
    acquired_at: datetime | None,
) -> dict[str, Any]:
    """Describe queueing and debounce timing before Workflow B decisioning."""

    message_times = sorted(message.at for message in session.messages)
    first_message_at = message_times[0] if message_times else None
    last_message_at = message_times[-1] if message_times else None
    debounce_expires_at = session.debounce_expires_at
    pending_started_at = _parse_optional_datetime(session.pending_escalation_metadata.get("startedAt"))
    pending_expires_at = session.pending_escalation_expires_at

    return {
        "firstMessageAt": _normalize_utc_datetime(first_message_at).isoformat() if first_message_at is not None else None,
        "lastMessageAt": _normalize_utc_datetime(last_message_at).isoformat() if last_message_at is not None else None,
        "debounceExpiresAt": _normalize_utc_datetime(debounce_expires_at).isoformat(),
        "pendingEscalationStartedAt": _normalize_utc_datetime(pending_started_at).isoformat()
        if pending_started_at is not None
        else None,
        "pendingEscalationExpiresAt": _normalize_utc_datetime(pending_expires_at).isoformat()
        if pending_expires_at is not None
        else None,
        "workflowBStartedAt": _normalize_utc_datetime(workflow_started_at).isoformat(),
        "sessionAcquiredAt": _normalize_utc_datetime(acquired_at).isoformat() if acquired_at is not None else None,
        "durationsMs": {
            "messageWindowSpan": _duration_ms_between(first_message_at, last_message_at),
            "lastMessageToDebounceExpiry": _duration_ms_between(last_message_at, debounce_expires_at),
            "lastMessageToPendingEscalationStart": _duration_ms_between(last_message_at, pending_started_at),
            "lastMessageToPendingEscalationExpiry": _duration_ms_between(last_message_at, pending_expires_at),
            "pendingEscalationStartToExpiry": _duration_ms_between(pending_started_at, pending_expires_at),
            "pendingEscalationExpiryToWorkflowBStart": _duration_ms_between(pending_expires_at, workflow_started_at),
            "lastMessageToWorkflowBStart": _duration_ms_between(last_message_at, workflow_started_at),
            "debounceExpiryToWorkflowBStart": _duration_ms_between(debounce_expires_at, workflow_started_at),
            "lastMessageToSessionAcquire": _duration_ms_between(last_message_at, acquired_at),
            "debounceExpiryToSessionAcquire": _duration_ms_between(debounce_expires_at, acquired_at),
        },
    }


async def _openai_match(
    conversation: ConversationView,
    entries: list[KnowledgeEntry],
    *,
    settings: Settings,
    trace: LatencyTrace | None = None,
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
    if trace is None:
        candidate_payload = [
            {
                "index": index,
                "question": entry.question,
                "answer": entry.answer,
                "tags": list(entry.tags),
            }
            for index, entry in enumerate(candidates)
        ]
    else:
        with trace.step("workflow_b.matcher.prepare_candidates") as step:
            candidate_payload = [
                {
                    "index": index,
                    "question": entry.question,
                    "answer": entry.answer,
                    "tags": list(entry.tags),
                }
                for index, entry in enumerate(candidates)
            ]
            step["candidateCount"] = len(candidate_payload)

    system_prompt = (
        "You rank FAQ candidates for customer-support automation. "
        "activeQuestion is the only text that should drive candidate selection and answer decision making. "
        "context is archived history from previous processed windows and must never override activeQuestion. "
        "Use context only to clarify references when activeQuestion clearly points back to earlier history. "
        "If activeQuestion alone is unclear or not safely answerable from the candidates, return no match. "
        "Return valid JSON only with keys bestIndex, similarityScore, and reason. "
        "bestIndex must be an integer index from the candidates list or null if none match. "
        "similarityScore must be a number between 0 and 1, or between 0 and 100, or null when there is no safe match."
    )
    user_prompt = json.dumps(
        {
            "activeQuestion": conversation.active_question,
            "activeMessages": conversation.active_messages,
            "context": conversation.context,
            "coreRule": "Use activeQuestion for decision making. Do not answer from context unless activeQuestion clearly refers back to it.",
            "candidates": candidate_payload,
        },
        ensure_ascii=True,
    )

    if trace is None:
        response = await generate_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            settings=settings,
            temperature=0.0,
            max_tokens=200,
        )
    else:
        with trace.step("workflow_b.matcher.openai_completion", candidateCount=len(candidate_payload)):
            response = await generate_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                settings=settings,
                temperature=0.0,
                max_tokens=200,
            )

    if trace is None:
        parsed = json.loads(_strip_json_fence(response))
    else:
        with trace.step("workflow_b.matcher.parse_response"):
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


async def _load_latest_session(database: Database, session: SessionState) -> SessionState:
    """Reload the live session document for race-aware merge decisions."""

    latest_session = await database.session_state.get_by_identity(
        session.tenant_id,
        session.client_id,
        session.user_id,
    )
    if latest_session is None or latest_session.id != session.id:
        raise DatabaseError("failed to load session for race-aware merge")
    return latest_session


def _messages_changed_since_acquire(session: SessionState, latest_session: SessionState) -> bool:
    """Return whether a newer inbound mutated the session after Workflow B acquired it."""

    if len(latest_session.messages) != len(session.messages):
        return True

    for current_message, latest_message in zip(session.messages, latest_session.messages, strict=False):
        if current_message.text != latest_message.text or current_message.at != latest_message.at:
            return True

    return latest_session.updated_at > session.updated_at


def _pending_escalation_is_stale(session: SessionState) -> bool:
    """Return whether pending escalation started before the latest inbound message arrived."""

    pending_started_at = _parse_optional_datetime(session.pending_escalation_metadata.get("startedAt"))
    if pending_started_at is None:
        return False

    message_times = [message.at for message in session.messages]
    if not message_times:
        return False

    last_message_at = max(message_times)
    return _normalize_utc_datetime(last_message_at) > pending_started_at


def _audit_metadata(
    *,
    identity: IdentityFrame,
    session: SessionState,
    decision: str,
    latency_ms: int,
    reason: str,
    provider_name: str | None,
    threshold: float | None = None,
    similarity_score: float | None = None,
    similarity_outcome: str = "not_evaluated",
    candidate_found: bool = False,
    domain_id: str | None = None,
    matcher_metadata: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build consistent audit metadata for governance logs."""

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
    if domain_id is not None:
        metadata["domainId"] = domain_id
    if matcher_metadata:
        metadata.update(dict(matcher_metadata))
    if extra:
        metadata.update(dict(extra))
    return metadata


async def _archive_processed_window(
    database: Database,
    session: SessionState,
    *,
    active_question: str,
    now: datetime,
    escalate: bool | None = None,
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

    update_payload: dict[str, Any] = {
        "context": next_context,
        "messages": remaining_messages,
        "updated_at": latest_session.updated_at if has_unprocessed_messages else now,
        "debounce_expires_at": latest_session.debounce_expires_at,
        "processing": False if has_unprocessed_messages else True,
        "pending_escalation": False,
        "pending_escalation_expires_at": None,
        "pending_escalation_metadata": {},
    }
    if escalate is not None:
        update_payload["escalate"] = escalate

    updated_session = await database.session_state.update_by_id(
        session.id,
        update_payload,
    )
    if updated_session is None:
        raise DatabaseError("failed to archive processed session window")
    return updated_session


async def _start_pending_escalation(
    database: Database,
    session: SessionState,
    *,
    now: datetime,
    grace_seconds: int,
    reason: str,
    target: EscalationTarget,
    timing_metadata: Mapping[str, Any],
    conversation: ConversationView,
    domain_id: str | None,
    threshold: float | None,
    similarity_score: float | None,
    similarity_outcome: str,
    candidate_found: bool,
    matcher_metadata: Mapping[str, Any] | None = None,
    matched_question: str | None = None,
) -> SessionState:
    """Mark the session as pending escalation so new inbound can still reopen it."""

    if session.id is None:
        raise DatabaseError("ready session missing id")

    latest_session = await _load_latest_session(database, session)
    if _messages_changed_since_acquire(session, latest_session):
        updated_session = await database.session_state.update_by_id(
            session.id,
            {"processing": False},
        )
        if updated_session is None:
            raise DatabaseError("failed to release superseded session")
        return updated_session

    pending_expires_at = now + timedelta(seconds=grace_seconds)
    updated_session = await database.session_state.update_by_id(
        session.id,
        {
            "processing": False,
            "pending_escalation": True,
            "pending_escalation_expires_at": pending_expires_at,
            "pending_escalation_metadata": {
                "reason": reason,
                "target": target.value,
                "domainId": domain_id,
                "threshold": threshold,
                "similarityScore": similarity_score,
                "similarityOutcome": similarity_outcome,
                "candidateFound": candidate_found,
                "matcherMetadata": dict(matcher_metadata or {}),
                "activeQuestion": conversation.active_question,
                "activeMessages": list(conversation.active_messages),
                "context": conversation.context,
                "matchedQuestion": matched_question,
                "startedAt": _normalize_utc_datetime(now).isoformat(),
                "expiresAt": _normalize_utc_datetime(pending_expires_at).isoformat(),
                "timing": dict(timing_metadata),
            },
        },
    )
    if updated_session is None:
        raise DatabaseError("failed to mark pending escalation")
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
    started_at = perf_counter()
    trace = LatencyTrace("workflow_b", started_at=current_time)
    acquired_session: SessionState | None = None

    try:
        with trace.step("workflow_b.session_state.acquire_ready_session") as acquire_step:
            acquired_session = await database.session_state.acquire_ready_session(current_time)
        if acquired_session is None:
            logger.debug(
                "workflow_b_no_ready_session",
                trace=trace.snapshot(outcome="idle"),
            )
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

        acquired_at = _parse_trace_timestamp(acquire_step.get("finishedAt"))
        with trace.step("workflow_b.identity.from_session"):
            identity = IdentityFrame(
                tenant_id=acquired_session.tenant_id,
                client_id=acquired_session.client_id,
                user_id=acquired_session.user_id,
            )
        with trace.step("workflow_b.conversation.build_view"):
            conversation = _build_conversation_view(acquired_session)
        active_question = conversation.active_question
        if not active_question:
            raise RoutingError("ready session has no searchable text")
        combined_text = active_question
        timing_metadata = {
            "workflow": trace.snapshot(),
            "messageWindow": _message_window_timing(
                acquired_session,
                workflow_started_at=current_time,
                acquired_at=acquired_at,
            ),
        }

        if acquired_session.pending_escalation and (
            acquired_session.pending_escalation_expires_at is not None
            and acquired_session.pending_escalation_expires_at <= current_time
        ):
            if _pending_escalation_is_stale(acquired_session):
                with trace.step("workflow_b.session_state.cancel_stale_pending_escalation"):
                    refreshed_session = await database.session_state.update_by_id(
                        acquired_session.id,
                        {
                            "processing": False,
                            "pending_escalation": False,
                            "pending_escalation_expires_at": None,
                            "pending_escalation_metadata": {},
                        },
                    )
                if refreshed_session is None:
                    raise DatabaseError("failed to cancel stale pending escalation")
                logger.info(
                    "workflow_b_pending_escalation_canceled",
                    sessionId=acquired_session.id,
                    tenantId=identity.tenant_id,
                    clientId=identity.client_id,
                    userId=identity.user_id,
                    trace=trace.snapshot(
                        outcome="pending_escalation_canceled",
                        messageWindow=timing_metadata["messageWindow"],
                    ),
                )
                return WorkflowBResult(
                    processed=False,
                    session_id=acquired_session.id,
                    decision=None,
                    combined_text=combined_text,
                    domain_id=None,
                    similarity_score=None,
                    answer_supplied=None,
                    outbound_send_result=None,
                    escalation_target=None,
                    reason="newer_messages_arrived",
                    matcher_used="pending_escalation",
                )

            with trace.step("workflow_b.pending_escalation.finalize"):
                pending_metadata = dict(acquired_session.pending_escalation_metadata)
                pending_reason = str(pending_metadata.get("reason", "pending_escalation_expired")).strip() or "pending_escalation_expired"
                pending_domain_id = pending_metadata.get("domainId")
                if not isinstance(pending_domain_id, str) or not pending_domain_id.strip():
                    pending_domain_id = None
                pending_similarity_score = pending_metadata.get("similarityScore")
                if not isinstance(pending_similarity_score, (int, float)):
                    pending_similarity_score = None
                pending_threshold = pending_metadata.get("threshold")
                if not isinstance(pending_threshold, (int, float)):
                    pending_threshold = None
                pending_similarity_outcome = str(pending_metadata.get("similarityOutcome", "not_evaluated"))
                pending_candidate_found = bool(pending_metadata.get("candidateFound", False))
                pending_matcher_metadata = pending_metadata.get("matcherMetadata")
                if not isinstance(pending_matcher_metadata, Mapping):
                    pending_matcher_metadata = {}
                pending_target = pending_metadata.get("target")
                if not isinstance(pending_target, str) or not pending_target.strip():
                    pending_target = EscalationTarget.HUMAN_REVIEW.value

                escalation = request_escalation(
                    identity,
                    combined_text,
                    reason=pending_reason,
                    metadata={"domainId": pending_domain_id} if pending_domain_id is not None else None,
                )
            log = build_escalated_log(
                identity,
                combined_text,
                similarity_score=float(pending_similarity_score) if pending_similarity_score is not None else None,
                metadata=_audit_metadata(
                    identity=identity,
                    session=acquired_session,
                    decision=GovernanceDecision.ESCALATED.value,
                    latency_ms=int((perf_counter() - started_at) * 1000),
                    reason=escalation.reason,
                    provider_name=acquired_session.provider,
                    threshold=float(pending_threshold) if pending_threshold is not None else None,
                    similarity_score=float(pending_similarity_score) if pending_similarity_score is not None else None,
                    similarity_outcome=pending_similarity_outcome,
                    candidate_found=pending_candidate_found,
                    domain_id=pending_domain_id,
                    matcher_metadata=pending_matcher_metadata,
                    extra={
                        "timing": {
                            **timing_metadata,
                            "workflow": trace.snapshot(),
                        },
                        "target": pending_target,
                        "activeQuestion": pending_metadata.get("activeQuestion", conversation.active_question),
                        "activeMessages": pending_metadata.get("activeMessages", conversation.active_messages),
                        "context": pending_metadata.get("context", conversation.context),
                        "matchedQuestion": pending_metadata.get("matchedQuestion"),
                        "pendingEscalation": {
                            "startedAt": pending_metadata.get("startedAt"),
                            "expiresAt": pending_metadata.get("expiresAt"),
                        },
                    },
                ),
                timestamp=current_time,
            )
            with trace.step("workflow_b.governance_logs.create"):
                await database.governance_logs.create(log)
            with trace.step("workflow_b.session_state.archive_processed_window"):
                await _archive_processed_window(
                    database,
                    acquired_session,
                    active_question=conversation.active_question,
                    now=current_time,
                    escalate=True,
                )
            logger.info(
                "workflow_b_completed",
                decision=GovernanceDecision.ESCALATED.value,
                sessionId=acquired_session.id,
                tenantId=identity.tenant_id,
                clientId=identity.client_id,
                userId=identity.user_id,
                domainId=pending_domain_id,
                similarityScore=pending_similarity_score,
                trace=trace.snapshot(
                    outcome=GovernanceDecision.ESCALATED.value,
                    messageWindow=timing_metadata["messageWindow"],
                ),
            )
            return WorkflowBResult(
                processed=True,
                session_id=acquired_session.id,
                decision=GovernanceDecision.ESCALATED,
                combined_text=combined_text,
                domain_id=pending_domain_id,
                similarity_score=float(pending_similarity_score) if pending_similarity_score is not None else None,
                answer_supplied=None,
                outbound_send_result=None,
                escalation_target=escalation.target,
                reason=escalation.reason,
                matcher_used="pending_escalation",
            )

        with trace.step("workflow_b.tenants.get_by_tenant_id"):
            tenant_document = await database.tenants.get_by_tenant_id(acquired_session.tenant_id)
        raw_domains = tenant_document.get("domains", []) if isinstance(tenant_document, Mapping) else []
        fallback_domain_id = _fallback_domain_id(tenant_document)

        with trace.step("workflow_b.config.resolve_threshold"):
            try:
                threshold = get_tenant_confidence_threshold(tenant_document)
            except ValueError:
                threshold = runtime_settings.SIMILARITY_THRESHOLD

        with trace.step("workflow_b.domain.choose_domain"):
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
            with trace.step("workflow_b.session_state.mark_pending_escalation"):
                updated_session = await _start_pending_escalation(
                    database,
                    acquired_session,
                    now=current_time,
                    grace_seconds=runtime_settings.ESCALATION_GRACE_SECONDS,
                    reason=escalation.reason,
                    target=escalation.target,
                    timing_metadata=timing_metadata,
                    conversation=conversation,
                    domain_id=None,
                    threshold=threshold,
                    similarity_score=None,
                    similarity_outcome="not_evaluated",
                    candidate_found=False,
                )
            if not updated_session.pending_escalation:
                logger.info(
                    "workflow_b_requeued_due_to_newer_messages",
                    sessionId=acquired_session.id,
                    tenantId=identity.tenant_id,
                    clientId=identity.client_id,
                    userId=identity.user_id,
                    trace=trace.snapshot(
                        outcome="superseded_by_newer_messages",
                        messageWindow=timing_metadata["messageWindow"],
                    ),
                )
                return WorkflowBResult(
                    processed=False,
                    session_id=acquired_session.id,
                    decision=None,
                    combined_text=combined_text,
                    domain_id=None,
                    similarity_score=None,
                    answer_supplied=None,
                    outbound_send_result=None,
                    escalation_target=None,
                    reason="newer_messages_arrived",
                    matcher_used="domain_gate",
                )
            logger.info(
                "workflow_b_pending_escalation_started",
                sessionId=acquired_session.id,
                tenantId=identity.tenant_id,
                clientId=identity.client_id,
                userId=identity.user_id,
                domainId=None,
                pendingEscalationExpiresAt=updated_session.pending_escalation_expires_at.isoformat()
                if updated_session.pending_escalation_expires_at is not None
                else None,
                trace=trace.snapshot(
                    outcome="pending_escalation",
                    messageWindow=timing_metadata["messageWindow"],
                ),
            )
            return WorkflowBResult(
                processed=True,
                session_id=acquired_session.id,
                decision=None,
                combined_text=combined_text,
                domain_id=None,
                similarity_score=None,
                answer_supplied=None,
                outbound_send_result=None,
                escalation_target=escalation.target,
                reason=escalation.reason,
                matcher_used="domain_gate",
            )

        with trace.step("workflow_b.knowledge_base.list_active_by_tenant_and_domain", domainId=domain_id) as step:
            entries = await database.knowledge_base.list_active_by_tenant_and_domain(
                acquired_session.tenant_id,
                domain_id,
            )
            step["entryCount"] = len(entries)
        openai_match = await _openai_match(
            conversation,
            entries,
            settings=runtime_settings,
            trace=trace,
        )
        with trace.step("workflow_b.similarity.evaluate"):
            similarity_decision = evaluate_similarity(
                openai_match.score,
                threshold,
                candidate_found=openai_match.entry is not None,
            )
        matcher_metadata = _matcher_metadata(openai_match)

        if similarity_decision.should_answer and openai_match.entry is not None:
            matched_entry = openai_match.entry
            with trace.step(
                "workflow_b.outbound.send_answer_reply",
                provider=acquired_session.provider or runtime_settings.WHATSAPP_PROVIDER,
            ):
                send_result = await _send_answer_reply(
                    identity,
                    matched_entry.answer,
                    provider_name=acquired_session.provider,
                    settings=runtime_settings,
                )
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
                    domain_id=domain_id,
                    matcher_metadata=matcher_metadata,
                    extra={
                        "timing": {
                            **timing_metadata,
                            "workflow": trace.snapshot(),
                        },
                        "activeQuestion": conversation.active_question,
                        "activeMessages": conversation.active_messages,
                        "context": conversation.context,
                        "matchedQuestion": matched_entry.question,
                        "delivery": {
                            "provider": send_result.provider,
                            "status": send_result.status,
                            "externalMessageId": send_result.external_message_id,
                        },
                    },
                ),
                timestamp=current_time,
            )
            with trace.step("workflow_b.governance_logs.create"):
                await database.governance_logs.create(log)
            with trace.step("workflow_b.session_state.archive_processed_window"):
                await _archive_processed_window(
                    database,
                    acquired_session,
                    active_question=conversation.active_question,
                    now=current_time,
                )
            logger.info(
                "workflow_b_completed",
                decision=GovernanceDecision.ANSWERED.value,
                sessionId=acquired_session.id,
                tenantId=identity.tenant_id,
                clientId=identity.client_id,
                userId=identity.user_id,
                domainId=domain_id,
                similarityScore=similarity_decision.score,
                trace=trace.snapshot(
                    outcome=GovernanceDecision.ANSWERED.value,
                    messageWindow=timing_metadata["messageWindow"],
                ),
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
        with trace.step("workflow_b.session_state.mark_pending_escalation"):
            updated_session = await _start_pending_escalation(
                database,
                acquired_session,
                now=current_time,
                grace_seconds=runtime_settings.ESCALATION_GRACE_SECONDS,
                reason=similarity_decision.reason,
                target=escalation.target,
                timing_metadata=timing_metadata,
                conversation=conversation,
                domain_id=domain_id,
                threshold=threshold,
                similarity_score=similarity_decision.score,
                similarity_outcome=similarity_decision.outcome.value,
                candidate_found=openai_match.entry is not None,
                matcher_metadata=matcher_metadata,
                matched_question=openai_match.entry.question if openai_match.entry is not None else None,
            )
        if not updated_session.pending_escalation:
            logger.info(
                "workflow_b_requeued_due_to_newer_messages",
                sessionId=acquired_session.id,
                tenantId=identity.tenant_id,
                clientId=identity.client_id,
                userId=identity.user_id,
                domainId=domain_id,
                trace=trace.snapshot(
                    outcome="superseded_by_newer_messages",
                    messageWindow=timing_metadata["messageWindow"],
                ),
            )
            return WorkflowBResult(
                processed=False,
                session_id=acquired_session.id,
                decision=None,
                combined_text=combined_text,
                domain_id=domain_id,
                similarity_score=similarity_decision.score,
                answer_supplied=None,
                outbound_send_result=None,
                escalation_target=None,
                reason="newer_messages_arrived",
                matcher_used="openai",
            )
        logger.info(
            "workflow_b_pending_escalation_started",
            sessionId=acquired_session.id,
            tenantId=identity.tenant_id,
            clientId=identity.client_id,
            userId=identity.user_id,
            domainId=domain_id,
            similarityScore=similarity_decision.score,
            pendingEscalationExpiresAt=updated_session.pending_escalation_expires_at.isoformat()
            if updated_session.pending_escalation_expires_at is not None
            else None,
            trace=trace.snapshot(
                outcome="pending_escalation",
                messageWindow=timing_metadata["messageWindow"],
            ),
        )
        return WorkflowBResult(
            processed=True,
            session_id=acquired_session.id,
            decision=None,
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
        if acquired_session is not None and acquired_session.id is not None:
            try:
                await database.session_state.update_by_id(
                    acquired_session.id,
                    {"processing": False},
                )
            except Exception:
                logger.exception(
                    "workflow_b_failed_to_release_processing_latch",
                    sessionId=acquired_session.id,
                )
        logger.exception(
            "workflow_b_failed",
            sessionId=acquired_session.id if acquired_session is not None else None,
            trace=trace.snapshot(outcome="failed"),
        )
        raise DatabaseError("workflow b processing failed") from exc
