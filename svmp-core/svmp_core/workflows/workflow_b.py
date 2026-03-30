"""Workflow B: process ready sessions and decide answer vs escalation."""

from __future__ import annotations

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
from svmp_core.models import GovernanceDecision, KnowledgeEntry, SessionState


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


def _pick_best_entry(query: str, entries: list[KnowledgeEntry]) -> tuple[KnowledgeEntry | None, float | None]:
    """Choose the strongest FAQ candidate using deterministic token overlap."""

    query_tokens = _tokenize(query)
    if not query_tokens:
        return None, None

    best_entry: KnowledgeEntry | None = None
    best_score = 0.0

    for entry in entries:
        entry_tokens = _tokenize(entry.question)
        if not entry_tokens:
            continue

        overlap = len(query_tokens & entry_tokens)
        score = overlap / len(query_tokens)
        if score > best_score:
            best_entry = entry
            best_score = score

    if best_entry is None or best_score <= 0:
        return None, None

    return best_entry, best_score


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
    escalation_target: EscalationTarget | None
    reason: str | None


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
                escalation_target=None,
                reason=None,
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
                escalation_target=escalation.target,
                reason=escalation.reason,
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
                escalation_target=escalation.target,
                reason=escalation.reason,
            )

        entries = await database.knowledge_base.list_active_by_tenant_and_domain(
            acquired_session.tenant_id,
            domain_id,
        )
        best_entry, score = _pick_best_entry(combined_text, entries)
        similarity_decision = evaluate_similarity(
            score,
            threshold,
            candidate_found=best_entry is not None,
        )

        if similarity_decision.should_answer and best_entry is not None:
            log = build_answered_log(
                identity,
                combined_text,
                similarity_score=similarity_decision.score or 0.0,
                answer_supplied=best_entry.answer,
                metadata={"domainId": domain_id},
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
                answer_supplied=best_entry.answer,
                escalation_target=None,
                reason=similarity_decision.reason,
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
            escalation_target=escalation.target,
            reason=escalation.reason,
        )
    except Exception as exc:
        raise DatabaseError("workflow b processing failed") from exc
