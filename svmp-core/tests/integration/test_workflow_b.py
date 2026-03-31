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
from svmp_core.models import (
    GovernanceDecision,
    GovernanceLog,
    KnowledgeEntry,
    MessageItem,
    OutboundSendResult,
    SessionState,
)
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

    return Settings(
        _env_file=None,
        SIMILARITY_THRESHOLD=0.75,
        WHATSAPP_PROVIDER="normalized",
        OPENAI_MATCHER_CANDIDATE_LIMIT=8,
    )


def _ready_session(*, text: str, provider: str | None = None) -> SessionState:
    """Build a ready-to-process session state."""

    return SessionState(
        _id="session-ready-1",
        tenantId="Niyomilan",
        clientId="whatsapp",
        userId="9845891194",
        provider=provider,
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
async def test_workflow_b_answers_high_confidence_informational_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workflow B should answer, send, and log when OpenAI returns a confident match."""

    async def fake_generate_completion(**kwargs) -> str:
        return '{"bestIndex": 0, "similarityScore": 0.92, "reason": "candidate 0 directly answers the query"}'

    monkeypatch.setattr("svmp_core.workflows.workflow_b.generate_completion", fake_generate_completion)

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
    assert result.similarity_score == 0.92
    assert result.matcher_used == "openai"
    assert result.outbound_send_result is not None
    assert result.outbound_send_result.provider == "normalized"
    assert result.outbound_send_result.accepted is True

    written_logs = database.governance_logs.logs
    assert len(written_logs) == 1
    assert written_logs[0].decision == GovernanceDecision.ANSWERED
    assert written_logs[0].metadata["matcherUsed"] == "openai"
    assert written_logs[0].metadata["delivery"]["provider"] == "normalized"

    session = await database.session_state.get_by_identity("Niyomilan", "whatsapp", "9845891194")
    assert session is not None
    assert session.status == "open"
    assert session.processing is True


@pytest.mark.asyncio
async def test_workflow_b_escalates_low_confidence_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workflow B should escalate when OpenAI returns a weak match."""

    async def fake_generate_completion(**kwargs) -> str:
        return '{"bestIndex": 0, "similarityScore": 0.21, "reason": "candidate is weakly related"}'

    monkeypatch.setattr("svmp_core.workflows.workflow_b.generate_completion", fake_generate_completion)

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
    assert result.outbound_send_result is None
    assert result.escalation_target is not None
    assert result.matcher_used == "openai"

    written_logs = database.governance_logs.logs
    assert len(written_logs) == 1
    assert written_logs[0].decision == GovernanceDecision.ESCALATED
    assert written_logs[0].metadata["matcherUsed"] == "openai"


@pytest.mark.asyncio
async def test_workflow_b_wraps_internal_failures_and_keeps_session_latched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Internal failures should be wrapped without clearing the processing latch."""

    async def fake_generate_completion(**kwargs) -> str:
        return '{"bestIndex": 0, "similarityScore": 0.92, "reason": "candidate 0 directly answers the query"}'

    monkeypatch.setattr("svmp_core.workflows.workflow_b.generate_completion", fake_generate_completion)

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
    assert session.status == "open"
    assert session.processing is True


@pytest.mark.asyncio
async def test_workflow_b_sends_answer_via_active_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Answered results should send the supplied answer through the resolved provider."""

    captured: dict[str, Any] = {}

    async def fake_generate_completion(**kwargs) -> str:
        return '{"bestIndex": 0, "similarityScore": 0.92, "reason": "candidate 0 directly answers the query"}'

    class FakeProvider:
        name = "twilio"

        async def send_text(self, message, *, settings):
            captured["message"] = message
            captured["provider"] = settings.WHATSAPP_PROVIDER
            return OutboundSendResult(
                provider="twilio",
                accepted=True,
                status="accepted",
                externalMessageId="SM999",
            )

    monkeypatch.setattr("svmp_core.workflows.workflow_b.generate_completion", fake_generate_completion)
    monkeypatch.setattr("svmp_core.workflows.workflow_b.get_whatsapp_provider", lambda **kwargs: FakeProvider())

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
        settings=Settings(
            _env_file=None,
            SIMILARITY_THRESHOLD=0.75,
            WHATSAPP_PROVIDER="twilio",
            OPENAI_MATCHER_CANDIDATE_LIMIT=8,
        ),
        now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
    )

    assert result.outbound_send_result is not None
    assert result.outbound_send_result.provider == "twilio"
    assert result.outbound_send_result.external_message_id == "SM999"
    assert result.matcher_used == "openai"
    assert captured["provider"] == "twilio"
    assert captured["message"].tenant_id == "Niyomilan"
    assert captured["message"].client_id == "whatsapp"
    assert captured["message"].user_id == "9845891194"
    assert captured["message"].text == "We help customers."


@pytest.mark.asyncio
async def test_workflow_b_uses_session_provider_for_outbound_routing() -> None:
    """Outbound replies should follow the session provider, not just the global default."""

    captured: dict[str, Any] = {}

    class FakeProvider:
        name = "twilio"

        async def send_text(self, message, *, settings):
            captured["message"] = message
            captured["provider"] = settings.WHATSAPP_PROVIDER
            return OutboundSendResult(
                provider="twilio",
                accepted=True,
                status="accepted",
                externalMessageId="SM321",
            )

    database = ProcessingDatabase(
        sessions=[_ready_session(text="What do you do?", provider="twilio")],
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

    monkeypatch = pytest.MonkeyPatch()
    def fake_get_whatsapp_provider(**kwargs):
        captured["requested_provider"] = kwargs["requested_provider"]
        return FakeProvider()

    monkeypatch.setattr("svmp_core.workflows.workflow_b.get_whatsapp_provider", fake_get_whatsapp_provider)
    try:
        result = await run_workflow_b(
            database,
            settings=Settings(_env_file=None, SIMILARITY_THRESHOLD=0.75, WHATSAPP_PROVIDER="meta"),
            now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
        )
    finally:
        monkeypatch.undo()

    assert captured["requested_provider"] == "twilio"
    assert result.outbound_send_result is not None
    assert result.outbound_send_result.provider == "twilio"
