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
    IntentType,
    build_answered_log,
    build_escalated_log,
    choose_domain,
    evaluate_similarity,
    infer_intent,
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


async def _openai_match(
    query: str,
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

    candidate_limit = max(1, settings.OPENAI_MATCHER_CANDIDATE_LIMIT)
    candidates = entries[:candidate_limit]
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
            "Return valid JSON only with keys bestIndex, similarityScore, and reason. "
            "bestIndex must be an integer index from the candidates list or null if none match. "
            "similarityScore must be a number between 0 and 1 or null when there is no safe match."
        ),
        user_prompt=json.dumps(
            {
                "query": query,
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

    if not isinstance(similarity_score, (int, float)) or not 0 <= float(similarity_score) <= 1:
        raise RoutingError("OpenAI matcher returned an invalid similarity score")

    matched_entry = candidates[best_index]
    return MatcherResult(
        matcher="openai",
        entry=matched_entry,
        score=float(similarity_score),
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
        combined_text = _combine_messages(acquired_session)
        if not combined_text:
            raise RoutingError("ready session has no searchable text")

        tenant_document = await database.tenants.get_by_tenant_id(acquired_session.tenant_id)
        intent = infer_intent(combined_text)

        if intent != IntentType.INFORMATIONAL:
            escalation = request_escalation(
                identity,
                combined_text,
                reason=f"intent_{intent.value}",
                metadata={"intent": intent.value},
            )
            log = build_escalated_log(
                identity,
                combined_text,
                metadata={"intent": intent.value, "target": escalation.target.value},
                timestamp=current_time,
            )
            await database.governance_logs.create(log)
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
                matcher_used="intent_gate",
            )

        raw_domains = tenant_document.get("domains", []) if isinstance(tenant_document, Mapping) else []
        fallback_domain_id = _fallback_domain_id(tenant_document)

        try:
            threshold = get_tenant_confidence_threshold(tenant_document)
        except ValueError:
            threshold = runtime_settings.SIMILARITY_THRESHOLD

        try:
            domain_id = choose_domain(
                combined_text,
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
                metadata={"reason": "domain_unresolved", "target": escalation.target.value},
                timestamp=current_time,
            )
            await database.governance_logs.create(log)
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
            combined_text,
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
                matched_entry.answer,
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
                "reason": similarity_decision.reason,
                "target": escalation.target.value,
                **matcher_metadata,
            },
            timestamp=current_time,
        )
        await database.governance_logs.create(log)
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
