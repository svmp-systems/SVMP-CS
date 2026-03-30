"""Integration-style tests for Workflow B processing."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import pytest

from svmp_core.config import Settings
from svmp_core.db.base import (
    Database,
    GovernanceLogRepository,
    KnowledgeBaseRepository,
    SessionStateRepository,
    TenantRepository,
)
from svmp_core.exceptions import DatabaseError
from svmp_core.models import GovernanceDecision, GovernanceLog, KnowledgeEntry, MessageItem, SessionState
from svmp_core.workflows import run_workflow_b


class ProcessingSessionRepository(SessionStateRepository):
    """In-memory session repository with ready-session support."""

    def __init__(self, sessions: list[SessionState]) -> None:
        self._sessions = {session.id: session.model_copy(deep=True) for session in sessions}

    async def get_by_identity(self, tenant_id: str, client_id: str, user_id: str) -> SessionState | None:
        for session in self._sessions.values():
            if (
                session.tenant_id == tenant_id
                and session.client_id == client_id
                and session.user_id == user_id
                and session.status == "open"
            ):
                return session.model_copy(deep=True)
        return None

    async def create(self, session: SessionState) -> SessionState:
        self._sessions[session.id] = session.model_copy(deep=True)
        return session.model_copy(deep=True)

    async def update_by_id(self, session_id: str, data: Mapping[str, Any]) -> SessionState | None:
        current = self._sessions.get(session_id)
        if current is None:
            return None

        updated = current.model_copy(update=deepcopy(dict(data)), deep=True)
        self._sessions[session_id] = updated
        return updated.model_copy(deep=True)

    async def acquire_ready_session(self, now: datetime) -> SessionState | None:
        ready_sessions = [
            session
            for session in self._sessions.values()
            if session.status == "open"
            and session.processing is False
            and session.debounce_expires_at <= now
        ]
        if not ready_sessions:
            return None

        selected = sorted(ready_sessions, key=lambda session: session.debounce_expires_at)[0]
        selected.processing = True
        selected.updated_at = now
        return selected.model_copy(deep=True)

    async def delete_stale_sessions(self, before: datetime) -> int:
        raise NotImplementedError


class InMemoryKnowledgeRepository(KnowledgeBaseRepository):
    """Simple knowledge repo keyed by tenant/domain."""

    def __init__(self, entries: list[KnowledgeEntry]) -> None:
        self._entries = [entry.model_copy(deep=True) for entry in entries]

    async def list_active_by_tenant_and_domain(
        self,
        tenant_id: str,
        domain_id: str,
    ) -> list[KnowledgeEntry]:
        return [
            entry.model_copy(deep=True)
            for entry in self._entries
            if entry.tenant_id == tenant_id and entry.domain_id == domain_id and entry.active
        ]


class CapturingGovernanceRepository(GovernanceLogRepository):
    """Collect governance logs written by Workflow B."""

    def __init__(self, *, should_fail: bool = False) -> None:
        self.logs: list[GovernanceLog] = []
        self._should_fail = should_fail

    async def create(self, log: GovernanceLog) -> GovernanceLog:
        if self._should_fail:
            raise RuntimeError("governance write failed")
        stored = log.model_copy(deep=True)
        self.logs.append(stored)
        return stored


class InMemoryTenantRepository(TenantRepository):
    """Simple tenant repository keyed by tenant id."""

    def __init__(self, tenants: list[Mapping[str, Any]]) -> None:
        self._tenants = {tenant["tenantId"]: deepcopy(dict(tenant)) for tenant in tenants}

    async def get_by_tenant_id(self, tenant_id: str) -> Mapping[str, Any] | None:
        tenant = self._tenants.get(tenant_id)
        return deepcopy(tenant) if tenant is not None else None


class ProcessingDatabase(Database):
    """Database wrapper for Workflow B tests."""

    def __init__(
        self,
        *,
        sessions: list[SessionState],
        knowledge_entries: list[KnowledgeEntry],
        tenants: list[Mapping[str, Any]],
        governance_should_fail: bool = False,
    ) -> None:
        self._session_state = ProcessingSessionRepository(sessions)
        self._knowledge_base = InMemoryKnowledgeRepository(knowledge_entries)
        self._governance_logs = CapturingGovernanceRepository(should_fail=governance_should_fail)
        self._tenants = InMemoryTenantRepository(tenants)

    @property
    def session_state(self) -> SessionStateRepository:
        return self._session_state

    @property
    def knowledge_base(self) -> KnowledgeBaseRepository:
        return self._knowledge_base

    @property
    def governance_logs(self) -> GovernanceLogRepository:
        return self._governance_logs

    @property
    def tenants(self) -> TenantRepository:
        return self._tenants

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None


def _settings() -> Settings:
    """Return deterministic workflow settings for tests."""

    return Settings(_env_file=None, SIMILARITY_THRESHOLD=0.75)


def _ready_session(*, text: str) -> SessionState:
    """Build a ready-to-process session state."""

    return SessionState(
        _id="session-ready-1",
        tenantId="Niyomilan",
        clientId="whatsapp",
        userId="9845891194",
        processing=False,
        messages=[MessageItem(text=text, at=datetime(2026, 3, 30, 9, 55, tzinfo=timezone.utc))],
        createdAt=datetime(2026, 3, 30, 9, 55, tzinfo=timezone.utc),
        updatedAt=datetime(2026, 3, 30, 9, 55, tzinfo=timezone.utc),
        debounceExpiresAt=datetime(2026, 3, 30, 9, 59, tzinfo=timezone.utc),
    )


def _tenant(*, threshold: float = 0.75) -> dict[str, Any]:
    """Build a representative tenant document."""

    return {
        "tenantId": "Niyomilan",
        "domains": [
            {
                "domainId": "general",
                "name": "General",
                "description": "What we do, company details, and contact information",
                "keywords": ["what", "company", "contact"],
            }
        ],
        "settings": {"confidenceThreshold": threshold},
    }


@pytest.mark.asyncio
async def test_workflow_b_answers_high_confidence_informational_query() -> None:
    """Workflow B should answer and log when confidence is high enough."""

    database = ProcessingDatabase(
        sessions=[_ready_session(text="What do you do?")],
        knowledge_entries=[
            KnowledgeEntry(
                _id="faq-1",
                tenantId="Niyomilan",
                domainId="general",
                question="What do you do?",
                answer="We help customers.",
            )
        ],
        tenants=[_tenant(threshold=0.75)],
    )

    result = await run_workflow_b(
        database,
        settings=_settings(),
        now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
    )

    assert result.processed is True
    assert result.decision == GovernanceDecision.ANSWERED
    assert result.answer_supplied == "We help customers."
    assert result.similarity_score == 1.0

    written_logs = database.governance_logs.logs
    assert len(written_logs) == 1
    assert written_logs[0].decision == GovernanceDecision.ANSWERED


@pytest.mark.asyncio
async def test_workflow_b_escalates_low_confidence_query() -> None:
    """Workflow B should escalate and log when the FAQ match is weak."""

    database = ProcessingDatabase(
        sessions=[_ready_session(text="What are your opening hours?")],
        knowledge_entries=[
            KnowledgeEntry(
                _id="faq-1",
                tenantId="Niyomilan",
                domainId="general",
                question="What do you do?",
                answer="We help customers.",
            )
        ],
        tenants=[_tenant(threshold=0.75)],
    )

    result = await run_workflow_b(
        database,
        settings=_settings(),
        now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
    )

    assert result.processed is True
    assert result.decision == GovernanceDecision.ESCALATED
    assert result.answer_supplied is None
    assert result.escalation_target is not None

    written_logs = database.governance_logs.logs
    assert len(written_logs) == 1
    assert written_logs[0].decision == GovernanceDecision.ESCALATED


@pytest.mark.asyncio
async def test_workflow_b_wraps_internal_failures_and_releases_session() -> None:
    """Internal failures should be wrapped and release the processing lock for retry."""

    database = ProcessingDatabase(
        sessions=[_ready_session(text="What do you do?")],
        knowledge_entries=[
            KnowledgeEntry(
                _id="faq-1",
                tenantId="Niyomilan",
                domainId="general",
                question="What do you do?",
                answer="We help customers.",
            )
        ],
        tenants=[_tenant(threshold=0.75)],
        governance_should_fail=True,
    )

    with pytest.raises(DatabaseError, match="workflow b processing failed"):
        await run_workflow_b(
            database,
            settings=_settings(),
            now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
        )

    session = await database.session_state.get_by_identity("Niyomilan", "whatsapp", "9845891194")
    assert session is not None
    assert session.processing is False


@pytest.mark.asyncio
async def test_workflow_b_runs_openai_matcher_in_shadow_mode_without_overriding_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shadow mode should record the OpenAI comparison while keeping deterministic authority."""

    async def fake_generate_completion(**kwargs) -> str:
        return '{"bestIndex": 0, "similarityScore": 0.18, "reason": "weak faq match"}'

    monkeypatch.setattr(
        "svmp_core.workflows.workflow_b.generate_completion",
        fake_generate_completion,
    )

    database = ProcessingDatabase(
        sessions=[_ready_session(text="What do you do?")],
        knowledge_entries=[
            KnowledgeEntry(
                _id="faq-1",
                tenantId="Niyomilan",
                domainId="general",
                question="What do you do?",
                answer="We help customers.",
            )
        ],
        tenants=[_tenant(threshold=0.75)],
    )

    result = await run_workflow_b(
        database,
        settings=Settings(_env_file=None, SIMILARITY_THRESHOLD=0.75, OPENAI_SHADOW_MODE=True),
        now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
    )

    assert result.processed is True
    assert result.decision == GovernanceDecision.ANSWERED
    assert result.matcher_used == "deterministic"

    written_logs = database.governance_logs.logs
    assert len(written_logs) == 1
    comparison = written_logs[0].metadata["matcherComparison"]
    assert written_logs[0].metadata["matcherMode"] == "shadow"
    assert comparison["deterministic"]["matcher"] == "deterministic"
    assert comparison["openai"]["matcher"] == "openai"
    assert comparison["openai"]["score"] == pytest.approx(0.18)


@pytest.mark.asyncio
async def test_workflow_b_can_use_openai_matcher_authoritatively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When enabled, the OpenAI matcher should become the authoritative scorer."""

    async def fake_generate_completion(**kwargs) -> str:
        return '{"bestIndex": 0, "similarityScore": 0.92, "reason": "candidate 0 directly answers the query"}'

    monkeypatch.setattr(
        "svmp_core.workflows.workflow_b.generate_completion",
        fake_generate_completion,
    )

    database = ProcessingDatabase(
        sessions=[_ready_session(text="Can you tell me your weekday opening hours?")],
        knowledge_entries=[
            KnowledgeEntry(
                _id="faq-1",
                tenantId="Niyomilan",
                domainId="general",
                question="What do you do?",
                answer="We help customers.",
            ),
            KnowledgeEntry(
                _id="faq-2",
                tenantId="Niyomilan",
                domainId="general",
                question="Business opening times",
                answer="We are open from 9 AM to 6 PM on weekdays.",
            ),
        ],
        tenants=[_tenant(threshold=0.75)],
    )

    result = await run_workflow_b(
        database,
        settings=Settings(_env_file=None, SIMILARITY_THRESHOLD=0.75, USE_OPENAI_MATCHER=True),
        now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
    )

    assert result.processed is True
    assert result.decision == GovernanceDecision.ANSWERED
    assert result.matcher_used == "openai"
    assert result.answer_supplied == "We are open from 9 AM to 6 PM on weekdays."

    written_logs = database.governance_logs.logs
    assert len(written_logs) == 1
    assert written_logs[0].metadata["matcherMode"] == "openai"
    assert written_logs[0].metadata["matcherUsed"] == "openai"
