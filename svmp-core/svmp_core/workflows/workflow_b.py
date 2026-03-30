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
from svmp_core.integrations import generate_completion
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


def _rank_entries(query: str, entries: list[KnowledgeEntry]) -> list[tuple[KnowledgeEntry, float]]:
    """Rank entries by deterministic token-overlap score."""

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    ranked: list[tuple[KnowledgeEntry, float]] = []
    for entry in entries:
        entry_tokens = _tokenize(entry.question)
        if not entry_tokens:
            continue

        overlap = len(query_tokens & entry_tokens)
        score = overlap / len(query_tokens)
        ranked.append((entry, score))

    ranked.sort(key=lambda item: (item[1], item[0].question.lower()), reverse=True)
    return ranked


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
    """Normalized candidate-match result from deterministic or OpenAI matching."""

    matcher: str
    entry: KnowledgeEntry | None
    score: float | None
    reason: str
    metadata: dict[str, Any]


def _serialize_matcher_result(result: MatcherResult | None) -> dict[str, Any] | None:
    """Convert matcher results into governance-safe metadata."""

    if result is None:
        return None

    question = result.entry.question if result.entry is not None else None
    entry_id = result.entry.id if result.entry is not None else None

    payload = {
        "matcher": result.matcher,
        "question": question,
        "entryId": entry_id,
        "score": result.score,
        "reason": result.reason,
    }
    payload.update(result.metadata)
    return payload


def _deterministic_match(query: str, entries: list[KnowledgeEntry]) -> MatcherResult:
    """Return the deterministic baseline match used today."""

    best_entry, score = _pick_best_entry(query, entries)
    ranked = _rank_entries(query, entries)

    if best_entry is None or score is None:
        return MatcherResult(
            matcher="deterministic",
            entry=None,
            score=None,
            reason="no candidate match available",
            metadata={"candidatesConsidered": len(entries)},
        )

    return MatcherResult(
        matcher="deterministic",
        entry=best_entry,
        score=score,
        reason="selected by token-overlap baseline",
        metadata={
            "candidatesConsidered": len(entries),
            "topCandidateQuestions": [entry.question for entry, _ in ranked[:3]],
        },
    )


async def _openai_match(
    query: str,
    entries: list[KnowledgeEntry],
    *,
    settings: Settings,
) -> MatcherResult:
    """Use the configured OpenAI model to choose the best FAQ candidate."""

    if not entries:
        return MatcherResult(
            matcher="openai",
            entry=None,
            score=None,
            reason="no candidate match available",
            metadata={"candidatesConsidered": 0},
        )

    ranked = _rank_entries(query, entries)
    candidate_limit = max(1, settings.OPENAI_MATCHER_CANDIDATE_LIMIT)
    candidates = ranked[:candidate_limit] if ranked else [(entry, 0.0) for entry in entries[:candidate_limit]]
    candidate_payload = [
        {
            "index": index,
            "question": entry.question,
            "answer": entry.answer,
            "tags": list(entry.tags),
            "deterministicScore": round(score, 4),
        }
        for index, (entry, score) in enumerate(candidates)
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

    matched_entry = candidates[best_index][0]
    return MatcherResult(
        matcher="openai",
        entry=matched_entry,
        score=float(similarity_score),
        reason=reason,
        metadata={"candidatesConsidered": len(candidate_payload)},
    )


def _matcher_metadata(
    *,
    authoritative: MatcherResult,
    deterministic: MatcherResult,
    openai: MatcherResult | None,
    shadow_enabled: bool,
    openai_authoritative: bool,
) -> dict[str, Any]:
    """Build governance metadata describing matcher behavior and comparisons."""

    mode = "deterministic"
    if openai_authoritative:
        mode = "openai"
    elif shadow_enabled:
        mode = "shadow"

    metadata: dict[str, Any] = {
        "matcherMode": mode,
        "matcherUsed": authoritative.matcher,
        "matcherComparison": {
            "deterministic": _serialize_matcher_result(deterministic),
        },
    }

    if openai is not None:
        metadata["matcherComparison"]["openai"] = _serialize_matcher_result(openai)

    return metadata


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


async def _finalize_processed_session(database: Database, session_id: str, now: datetime) -> None:
    """Mark a processed session as closed so it is not picked up again."""

    updated = await database.session_state.update_by_id(
        session_id,
        {
            "status": "closed",
            "processing": False,
            "updated_at": now,
        },
    )
    if updated is None:
        raise DatabaseError("failed to finalize processed session")


async def _release_session_for_retry(database: Database, session_id: str, now: datetime) -> None:
    """Best-effort release of the processing lock after an internal failure."""

    try:
        await database.session_state.update_by_id(
            session_id,
            {
                "processing": False,
                "updated_at": now,
            },
        )
    except Exception:
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
            await _finalize_processed_session(database, acquired_session.id, current_time)
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
            await _finalize_processed_session(database, acquired_session.id, current_time)
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
                matcher_used="domain_gate",
            )

        entries = await database.knowledge_base.list_active_by_tenant_and_domain(
            acquired_session.tenant_id,
            domain_id,
        )
        deterministic_match = _deterministic_match(combined_text, entries)
        openai_match: MatcherResult | None = None
        authoritative_match = deterministic_match
        openai_authoritative = False

        if runtime_settings.USE_OPENAI_MATCHER or runtime_settings.OPENAI_SHADOW_MODE:
            try:
                openai_match = await _openai_match(
                    combined_text,
                    entries,
                    settings=runtime_settings,
                )
            except Exception as exc:
                openai_match = MatcherResult(
                    matcher="openai",
                    entry=None,
                    score=None,
                    reason="openai matcher failed; falling back to deterministic baseline",
                    metadata={"error": str(exc)},
                )

            if runtime_settings.USE_OPENAI_MATCHER and "error" not in openai_match.metadata:
                authoritative_match = openai_match
                openai_authoritative = True

        similarity_decision = evaluate_similarity(
            authoritative_match.score,
            threshold,
            candidate_found=authoritative_match.entry is not None,
        )
        matcher_metadata = _matcher_metadata(
            authoritative=authoritative_match,
            deterministic=deterministic_match,
            openai=openai_match,
            shadow_enabled=runtime_settings.OPENAI_SHADOW_MODE,
            openai_authoritative=openai_authoritative,
        )

        if similarity_decision.should_answer and authoritative_match.entry is not None:
            log = build_answered_log(
                identity,
                combined_text,
                similarity_score=similarity_decision.score or 0.0,
                answer_supplied=authoritative_match.entry.answer,
                metadata={
                    "domainId": domain_id,
                    **matcher_metadata,
                },
                timestamp=current_time,
            )
            await database.governance_logs.create(log)
            await _finalize_processed_session(database, acquired_session.id, current_time)
            return WorkflowBResult(
                processed=True,
                session_id=acquired_session.id,
                decision=GovernanceDecision.ANSWERED,
                combined_text=combined_text,
                domain_id=domain_id,
                similarity_score=similarity_decision.score,
                answer_supplied=authoritative_match.entry.answer,
                escalation_target=None,
                reason=similarity_decision.reason,
                matcher_used=authoritative_match.matcher,
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
        await _finalize_processed_session(database, acquired_session.id, current_time)
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
            matcher_used=authoritative_match.matcher,
        )
    except Exception as exc:
        if acquired_session is not None and acquired_session.id is not None:
            await _release_session_for_retry(database, acquired_session.id, current_time)
        raise DatabaseError("workflow b processing failed") from exc
