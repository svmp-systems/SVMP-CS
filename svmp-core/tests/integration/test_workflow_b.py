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
        pending_sessions = [
            session
            for session in self._sessions.values()
            if session.status == "open"
            and session.processing is False
            and session.escalate is False
            and session.pending_escalation is True
            and session.pending_escalation_expires_at is not None
            and session.pending_escalation_expires_at <= now
        ]
        if pending_sessions:
            selected = sorted(pending_sessions, key=lambda session: session.pending_escalation_expires_at)[0]
            selected.processing = True
            selected.updated_at = now
            return selected.model_copy(deep=True)

        ready_sessions = [
            session
            for session in self._sessions.values()
            if session.status == "open"
            and session.processing is False
            and session.escalate is False
            and session.pending_escalation is False
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


def _ready_session(
    *,
    text: str | None = None,
    texts: list[str] | None = None,
    provider: str | None = None,
    context: list[str] | None = None,
) -> SessionState:
    """Build a ready-to-process session state."""

    message_texts = texts or ([text] if text is not None else None)
    if not message_texts:
        raise ValueError("expected at least one message text")

    return SessionState(
        _id="session-ready-1",
        tenantId="Niyomilan",
        clientId="whatsapp",
        userId="9845891194",
        provider=provider,
        processing=False,
        context=list(context or []),
        messages=[
            MessageItem(text=message_text, at=datetime(2026, 3, 30, 9, 55, tzinfo=timezone.utc))
            for message_text in message_texts
        ],
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
    assert written_logs[0].metadata["workflow"] == "workflow_b"
    assert written_logs[0].metadata["decision"] == "answered"
    assert written_logs[0].metadata["decisionReason"] == "score meets or exceeds threshold"
    assert written_logs[0].metadata["sessionId"] == "session-ready-1"
    assert written_logs[0].metadata["provider"] is None
    assert written_logs[0].metadata["identity"] == {
        "tenantId": "Niyomilan",
        "clientId": "whatsapp",
        "userId": "9845891194",
    }
    assert written_logs[0].metadata["similarity"] == {
        "score": 0.92,
        "threshold": 0.75,
        "outcome": "pass",
        "candidateFound": True,
    }
    timing = written_logs[0].metadata["timing"]
    assert timing["messageWindow"]["lastMessageAt"] == "2026-03-30T09:55:00+00:00"
    assert timing["messageWindow"]["debounceExpiresAt"] == "2026-03-30T09:59:00+00:00"
    assert timing["messageWindow"]["durationsMs"]["lastMessageToWorkflowBStart"] == 300000
    assert timing["messageWindow"]["durationsMs"]["debounceExpiryToWorkflowBStart"] == 60000
    assert "workflow_b.matcher.openai_completion" in {
        step["name"] for step in timing["workflow"]["steps"]
    }
    assert isinstance(written_logs[0].metadata["latencyMs"], int)

    session = await database.session_state.get_by_identity("Niyomilan", "whatsapp", "9845891194")
    assert session is not None
    assert session.status == "open"
    assert session.processing is True
    assert session.escalate is False
    assert session.messages == []
    assert session.context == ["What do you do?"]


@pytest.mark.asyncio
async def test_workflow_b_escalates_low_confidence_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Low-confidence matches should enter grace first, then escalate if no new message arrives."""

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

    first_result = await run_workflow_b(
        database,
        settings=Settings(_env_file=None, SIMILARITY_THRESHOLD=0.75, WHATSAPP_PROVIDER="normalized", OPENAI_MATCHER_CANDIDATE_LIMIT=8, ESCALATION_GRACE_SECONDS=5),
        now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
    )

    assert first_result.processed is True
    assert first_result.decision is None
    assert first_result.answer_supplied is None
    assert first_result.outbound_send_result is None
    assert first_result.escalation_target is not None
    assert first_result.matcher_used == "openai"

    written_logs = database.governance_logs.logs
    assert written_logs == []

    pending_session = await database.session_state.get_by_identity("Niyomilan", "whatsapp", "9845891194")
    assert pending_session is not None
    assert pending_session.escalate is False
    assert pending_session.pending_escalation is True
    assert pending_session.pending_escalation_expires_at == datetime(2026, 3, 30, 10, 0, 5, tzinfo=timezone.utc)
    assert pending_session.pending_escalation_metadata["reason"] == "score below threshold"
    assert pending_session.pending_escalation_metadata["matchedQuestion"] == "What do you do?"

    final_result = await run_workflow_b(
        database,
        settings=Settings(_env_file=None, SIMILARITY_THRESHOLD=0.75, WHATSAPP_PROVIDER="normalized", OPENAI_MATCHER_CANDIDATE_LIMIT=8, ESCALATION_GRACE_SECONDS=5),
        now=datetime(2026, 3, 30, 10, 0, 6, tzinfo=timezone.utc),
    )

    assert final_result.processed is True
    assert final_result.decision == GovernanceDecision.ESCALATED
    assert final_result.answer_supplied is None
    assert final_result.outbound_send_result is None
    assert final_result.escalation_target is not None
    assert final_result.matcher_used == "pending_escalation"

    assert len(written_logs) == 1
    assert written_logs[0].decision == GovernanceDecision.ESCALATED
    assert written_logs[0].metadata["matcherUsed"] == "openai"
    assert written_logs[0].metadata["workflow"] == "workflow_b"
    assert written_logs[0].metadata["decision"] == "escalated"
    assert written_logs[0].metadata["decisionReason"] == "score below threshold"
    assert written_logs[0].metadata["similarity"] == {
        "score": 0.21,
        "threshold": 0.75,
        "outcome": "fail",
        "candidateFound": True,
    }
    timing = written_logs[0].metadata["timing"]
    assert timing["messageWindow"]["lastMessageAt"] == "2026-03-30T09:55:00+00:00"
    assert timing["messageWindow"]["pendingEscalationStartedAt"] == "2026-03-30T10:00:00+00:00"
    assert timing["messageWindow"]["pendingEscalationExpiresAt"] == "2026-03-30T10:00:05+00:00"
    assert timing["messageWindow"]["durationsMs"]["debounceExpiryToWorkflowBStart"] == 66000
    assert timing["messageWindow"]["durationsMs"]["pendingEscalationStartToExpiry"] == 5000
    assert timing["messageWindow"]["durationsMs"]["pendingEscalationExpiryToWorkflowBStart"] == 1000
    assert "workflow_b.pending_escalation.finalize" in {
        step["name"] for step in timing["workflow"]["steps"]
    }
    assert written_logs[0].metadata["target"] == "human_review"
    assert written_logs[0].metadata["pendingEscalation"] == {
        "startedAt": "2026-03-30T10:00:00+00:00",
        "expiresAt": "2026-03-30T10:00:05+00:00",
    }
    assert isinstance(written_logs[0].metadata["latencyMs"], int)

    session = await database.session_state.get_by_identity("Niyomilan", "whatsapp", "9845891194")
    assert session is not None
    assert session.escalate is True
    assert session.pending_escalation is False


@pytest.mark.asyncio
async def test_workflow_b_skips_sessions_that_have_already_been_escalated() -> None:
    """Sessions marked with escalate=true should no longer be picked up by the bot."""

    database = ProcessingDatabase(
        sessions=[_ready_session(text="Can you still read this?").model_copy(update={"escalate": True}, deep=True)],
        knowledge_entries=[],
        tenants=[_tenant(threshold=0.75)],
    )

    result = await run_workflow_b(
        database,
        settings=_settings(),
        now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
    )

    assert result.processed is False
    assert result.decision is None
    assert database.governance_logs.logs == []


@pytest.mark.asyncio
async def test_workflow_b_restarts_debounce_if_new_message_arrives_during_pending_escalation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new inbound during the grace window should clear the pending escalation and allow a fresh answer pass."""

    responses = iter(
        [
            '{"bestIndex": 0, "similarityScore": 0.21, "reason": "candidate is weakly related"}',
            '{"bestIndex": 0, "similarityScore": 0.92, "reason": "candidate 0 directly answers the query"}',
        ]
    )

    async def fake_generate_completion(**kwargs) -> str:
        return next(responses)

    monkeypatch.setattr("svmp_core.workflows.workflow_b.generate_completion", fake_generate_completion)

    database = ProcessingDatabase(
        sessions=[_ready_session(text="What are your opening hours?")],
        knowledge_entries=[
            KnowledgeEntry(
                _id="faq-1",
                tenantId="Niyomilan",
                domainId="general",
                question="What are your opening hours and address?",
                answer="We are open 10 AM to 8 PM and are located in Koramangala.",
            )
        ],
        tenants=[_tenant(threshold=0.75)],
    )

    first_result = await run_workflow_b(
        database,
        settings=Settings(_env_file=None, SIMILARITY_THRESHOLD=0.75, WHATSAPP_PROVIDER="normalized", OPENAI_MATCHER_CANDIDATE_LIMIT=8, ESCALATION_GRACE_SECONDS=5),
        now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
    )

    assert first_result.decision is None

    seeded = await database.session_state.get_by_identity("Niyomilan", "whatsapp", "9845891194")
    assert seeded is not None
    assert seeded.id is not None
    updated = await database.session_state.update_by_id(
        seeded.id,
        {
            "messages": [
                *seeded.messages,
                MessageItem(text="and where are you located?", at=datetime(2026, 3, 30, 10, 0, 2, tzinfo=timezone.utc)),
            ],
            "updated_at": datetime(2026, 3, 30, 10, 0, 2, tzinfo=timezone.utc),
            "debounce_expires_at": datetime(2026, 3, 30, 10, 0, 4, tzinfo=timezone.utc),
            "processing": False,
            "pending_escalation": False,
            "pending_escalation_expires_at": None,
            "pending_escalation_metadata": {},
        },
    )
    assert updated is not None

    second_result = await run_workflow_b(
        database,
        settings=Settings(_env_file=None, SIMILARITY_THRESHOLD=0.75, WHATSAPP_PROVIDER="normalized", OPENAI_MATCHER_CANDIDATE_LIMIT=8, ESCALATION_GRACE_SECONDS=5),
        now=datetime(2026, 3, 30, 10, 0, 4, tzinfo=timezone.utc),
    )

    assert second_result.decision == GovernanceDecision.ANSWERED
    assert second_result.answer_supplied == "We are open 10 AM to 8 PM and are located in Koramangala."
    assert len(database.governance_logs.logs) == 1
    assert database.governance_logs.logs[0].decision == GovernanceDecision.ANSWERED


@pytest.mark.asyncio
async def test_workflow_b_does_not_start_pending_escalation_if_new_message_arrives_mid_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If a newer inbound arrives while Workflow B is still matching, the old run should not arm escalation."""

    database = ProcessingDatabase(
        sessions=[_ready_session(text="What are your opening hours?")],
        knowledge_entries=[
            KnowledgeEntry(
                _id="faq-1",
                tenantId="Niyomilan",
                domainId="general",
                question="What are your opening hours and address?",
                answer="We are open 10 AM to 8 PM and are located in Koramangala.",
            )
        ],
        tenants=[_tenant(threshold=0.75)],
    )

    responses = iter(
        [
            '{"bestIndex": 0, "similarityScore": 0.21, "reason": "candidate is weakly related"}',
            '{"bestIndex": 0, "similarityScore": 0.92, "reason": "candidate 0 directly answers the query"}',
        ]
    )

    async def fake_generate_completion(**kwargs) -> str:
        current = await database.session_state.get_by_identity("Niyomilan", "whatsapp", "9845891194")
        assert current is not None
        assert current.id is not None

        if len(current.messages) == 1:
            updated = await database.session_state.update_by_id(
                current.id,
                {
                    "messages": [
                        *current.messages,
                        MessageItem(text="and where are you located?", at=datetime(2026, 3, 30, 10, 0, 2, tzinfo=timezone.utc)),
                    ],
                    "updated_at": datetime(2026, 3, 30, 10, 0, 2, tzinfo=timezone.utc),
                    "debounce_expires_at": datetime(2026, 3, 30, 10, 0, 4, tzinfo=timezone.utc),
                    "processing": False,
                    "pending_escalation": False,
                    "pending_escalation_expires_at": None,
                    "pending_escalation_metadata": {},
                },
            )
            assert updated is not None

        return next(responses)

    monkeypatch.setattr("svmp_core.workflows.workflow_b.generate_completion", fake_generate_completion)

    first_result = await run_workflow_b(
        database,
        settings=Settings(_env_file=None, SIMILARITY_THRESHOLD=0.75, WHATSAPP_PROVIDER="normalized", OPENAI_MATCHER_CANDIDATE_LIMIT=8, ESCALATION_GRACE_SECONDS=5),
        now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
    )

    assert first_result.processed is False
    assert first_result.decision is None
    assert database.governance_logs.logs == []

    session_after_first_run = await database.session_state.get_by_identity("Niyomilan", "whatsapp", "9845891194")
    assert session_after_first_run is not None
    assert session_after_first_run.pending_escalation is False
    assert [message.text for message in session_after_first_run.messages] == [
        "What are your opening hours?",
        "and where are you located?",
    ]

    second_result = await run_workflow_b(
        database,
        settings=Settings(_env_file=None, SIMILARITY_THRESHOLD=0.75, WHATSAPP_PROVIDER="normalized", OPENAI_MATCHER_CANDIDATE_LIMIT=8, ESCALATION_GRACE_SECONDS=5),
        now=datetime(2026, 3, 30, 10, 0, 4, tzinfo=timezone.utc),
    )

    assert second_result.decision == GovernanceDecision.ANSWERED
    assert second_result.answer_supplied == "We are open 10 AM to 8 PM and are located in Koramangala."


@pytest.mark.asyncio
async def test_workflow_b_cancels_stale_pending_escalation_before_finalization() -> None:
    """Pending escalation should be canceled if a newer message arrived after the grace started."""

    stale_session = _ready_session(
        texts=["What are your opening hours?", "and where are you located?"],
    ).model_copy(
        update={
            "pending_escalation": True,
            "pending_escalation_expires_at": datetime(2026, 3, 30, 10, 0, 5, tzinfo=timezone.utc),
            "pending_escalation_metadata": {
                "reason": "score below threshold",
                "target": "human_review",
                "startedAt": "2026-03-30T10:00:00+00:00",
                "expiresAt": "2026-03-30T10:00:05+00:00",
            },
            "debounce_expires_at": datetime(2026, 3, 30, 10, 0, 3, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 3, 30, 10, 0, 2, tzinfo=timezone.utc),
        },
        deep=True,
    )
    stale_session.messages[0].at = datetime(2026, 3, 30, 9, 55, tzinfo=timezone.utc)
    stale_session.messages[1].at = datetime(2026, 3, 30, 10, 0, 2, tzinfo=timezone.utc)

    database = ProcessingDatabase(
        sessions=[stale_session],
        knowledge_entries=[],
        tenants=[_tenant(threshold=0.75)],
    )

    result = await run_workflow_b(
        database,
        settings=Settings(_env_file=None, SIMILARITY_THRESHOLD=0.75, WHATSAPP_PROVIDER="normalized", OPENAI_MATCHER_CANDIDATE_LIMIT=8, ESCALATION_GRACE_SECONDS=5),
        now=datetime(2026, 3, 30, 10, 0, 6, tzinfo=timezone.utc),
    )

    assert result.processed is False
    assert result.decision is None
    assert database.governance_logs.logs == []

    session = await database.session_state.get_by_identity("Niyomilan", "whatsapp", "9845891194")
    assert session is not None
    assert session.pending_escalation is False
    assert session.escalate is False


@pytest.mark.asyncio
async def test_workflow_b_normalizes_percentage_style_similarity_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Percentage-style scores from the model should normalize into 0-1 similarity values."""

    async def fake_generate_completion(**kwargs) -> str:
        return '{"bestIndex": 0, "similarityScore": 92, "reason": "candidate 0 directly answers the query"}'

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

    assert result.decision == GovernanceDecision.ANSWERED
    assert result.similarity_score == pytest.approx(0.92)


@pytest.mark.asyncio
async def test_workflow_b_prompt_uses_explicit_active_question_and_background_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matcher prompt should use activeQuestion explicitly and keep context secondary."""

    captured: dict[str, Any] = {}

    async def fake_generate_completion(**kwargs) -> str:
        captured["system_prompt"] = kwargs["system_prompt"]
        captured["user_prompt"] = kwargs["user_prompt"]
        return '{"bestIndex": 0, "similarityScore": 0.92, "reason": "candidate 0 directly answers the query"}'

    monkeypatch.setattr("svmp_core.workflows.workflow_b.generate_completion", fake_generate_completion)

    database = ProcessingDatabase(
        sessions=[
            _ready_session(
                texts=[
                    "What does Niyomilan do?",
                    "What is it trying to solve?",
                    "Why is it called Niyomilan?",
                ],
                context=["Hi there"],
            )
        ],
        knowledge_entries=[
            KnowledgeEntry(
                _id="faq-1",
                tenantId="Niyomilan",
                domainId="general",
                question="Why is it called Niyomilan?",
                answer="It comes from Sanskrit roots describing connection and purposeful engagement.",
            )
        ],
        tenants=[_tenant(threshold=0.75)],
    )

    await run_workflow_b(
        database,
        settings=_settings(),
        now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
    )

    assert "activeQuestion is the only text that should drive candidate selection" in captured["system_prompt"]
    assert "context is archived history from previous processed windows" in captured["system_prompt"]
    assert '"activeQuestion": "What does Niyomilan do? What is it trying to solve? Why is it called Niyomilan?"' in captured["user_prompt"]
    assert '"activeMessages": ["What does Niyomilan do?", "What is it trying to solve?", "Why is it called Niyomilan?"]' in captured["user_prompt"]
    assert '"context": "Hi there"' in captured["user_prompt"]
    assert '"combinedText"' not in captured["user_prompt"]


@pytest.mark.asyncio
async def test_workflow_b_uses_active_question_for_matching_and_archives_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model should receive the active question explicitly and archive that same window."""

    captured: dict[str, Any] = {}

    async def fake_generate_completion(**kwargs) -> str:
        captured["user_prompt"] = kwargs["user_prompt"]
        return '{"bestIndex": 1, "similarityScore": 0.92, "reason": "latest ask matches candidate 1"}'

    monkeypatch.setattr("svmp_core.workflows.workflow_b.generate_completion", fake_generate_completion)

    database = ProcessingDatabase(
        sessions=[
            _ready_session(
                texts=[
                    "What does Niyomilan do?",
                    "What is it trying to solve?",
                    "Why is it called Niyomilan?",
                ],
                context=["Older topic that should become context"],
            )
        ],
        knowledge_entries=[
            KnowledgeEntry(
                _id="faq-1",
                tenantId="Niyomilan",
                domainId="general",
                question="What does Niyomilan do?",
                answer="We help customers.",
            ),
            KnowledgeEntry(
                _id="faq-2",
                tenantId="Niyomilan",
                domainId="general",
                question="Why is it called Niyomilan?",
                answer="It comes from Sanskrit roots describing connection and purposeful engagement.",
            ),
        ],
        tenants=[_tenant(threshold=0.75)],
    )

    result = await run_workflow_b(
        database,
        settings=_settings(),
        now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
    )

    assert result.decision == GovernanceDecision.ANSWERED
    assert result.answer_supplied == "It comes from Sanskrit roots describing connection and purposeful engagement."
    assert '"activeQuestion": "What does Niyomilan do? What is it trying to solve? Why is it called Niyomilan?"' in captured["user_prompt"]
    assert '"activeMessages": ["What does Niyomilan do?", "What is it trying to solve?", "Why is it called Niyomilan?"]' in captured["user_prompt"]
    assert '"context": "Older topic that should become context"' in captured["user_prompt"]

    session = await database.session_state.get_by_identity("Niyomilan", "whatsapp", "9845891194")
    assert session is not None
    assert session.messages == []
    assert session.context == [
        "Older topic that should become context",
        "What does Niyomilan do? What is it trying to solve? Why is it called Niyomilan?",
    ]


@pytest.mark.asyncio
async def test_workflow_b_preserves_new_messages_that_arrive_during_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Archiving the processed window should not wipe newer inbound messages."""

    async def fake_generate_completion(**kwargs) -> str:
        return '{"bestIndex": 0, "similarityScore": 0.92, "reason": "candidate 0 directly answers the query"}'

    monkeypatch.setattr("svmp_core.workflows.workflow_b.generate_completion", fake_generate_completion)

    database = ProcessingDatabase(
        sessions=[_ready_session(text="What size are Stay bottles?")],
        knowledge_entries=[
            KnowledgeEntry(
                _id="faq-1",
                tenantId="Niyomilan",
                domainId="general",
                question="What size are Stay bottles?",
                answer="Most bottles are 100 mL.",
            )
        ],
        tenants=[_tenant(threshold=0.75)],
    )

    async def fake_send_answer_reply(identity, answer_text, *, provider_name, settings):
        seeded = await database.session_state.get_by_identity("Niyomilan", "whatsapp", "9845891194")
        assert seeded is not None
        assert seeded.id is not None
        updated = await database.session_state.update_by_id(
            seeded.id,
            {
                "messages": [
                    *seeded.messages,
                    MessageItem(text="Do you offer free shipping?", at=datetime(2026, 3, 30, 10, 0, 1, tzinfo=timezone.utc)),
                ],
                "updated_at": datetime(2026, 3, 30, 10, 0, 1, tzinfo=timezone.utc),
                "debounce_expires_at": datetime(2026, 3, 30, 10, 0, 3, tzinfo=timezone.utc),
                "processing": False,
            },
        )
        assert updated is not None
        return OutboundSendResult(
            provider="normalized",
            accepted=True,
            status="accepted",
            externalMessageId="SM123",
        )

    monkeypatch.setattr("svmp_core.workflows.workflow_b._send_answer_reply", fake_send_answer_reply)

    result = await run_workflow_b(
        database,
        settings=_settings(),
        now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
    )

    assert result.decision == GovernanceDecision.ANSWERED

    session = await database.session_state.get_by_identity("Niyomilan", "whatsapp", "9845891194")
    assert session is not None
    assert [message.text for message in session.messages] == ["Do you offer free shipping?"]
    assert session.context == ["What size are Stay bottles?"]
    assert session.processing is False


@pytest.mark.asyncio
async def test_workflow_b_sends_explicit_active_question_and_background_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matcher payload should use activeQuestion explicitly and never send combinedText."""

    captured: dict[str, Any] = {}

    async def fake_generate_completion(**kwargs) -> str:
        captured["system_prompt"] = kwargs["system_prompt"]
        captured["user_prompt"] = kwargs["user_prompt"]
        return '{"bestIndex": 0, "similarityScore": 0.92, "reason": "candidate 0 directly answers the query"}'

    monkeypatch.setattr("svmp_core.workflows.workflow_b.generate_completion", fake_generate_completion)

    database = ProcessingDatabase(
        sessions=[
            _ready_session(
                text="Are your perfumes for men, women, or unisex wear?",
                context=["What size are stay perfume bottles ?"],
            )
        ],
        knowledge_entries=[
            KnowledgeEntry(
                _id="faq-1",
                tenantId="Niyomilan",
                domainId="general",
                question="Are your perfumes for men, women, or unisex wear?",
                answer="We offer men's, women's, and unisex fragrances.",
            )
        ],
        tenants=[_tenant(threshold=0.75)],
    )

    await run_workflow_b(
        database,
        settings=_settings(),
        now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
    )

    assert "activeQuestion is the only text that should drive candidate selection" in captured["system_prompt"]
    assert '"activeQuestion": "Are your perfumes for men, women, or unisex wear?"' in captured["user_prompt"]
    assert '"activeMessages": ["Are your perfumes for men, women, or unisex wear?"]' in captured["user_prompt"]
    assert '"context": "What size are stay perfume bottles ?"' in captured["user_prompt"]
    assert '"combinedText"' not in captured["user_prompt"]


@pytest.mark.asyncio
async def test_workflow_b_wraps_internal_failures_and_keeps_session_latched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Internal failures should be wrapped and release the processing latch for retry."""

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
    assert session.processing is False


@pytest.mark.asyncio
async def test_workflow_b_routes_answer_through_session_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Answered results should send through the provider stored on the session."""

    captured: dict[str, Any] = {}

    async def fake_generate_completion(**kwargs) -> str:
        return '{"bestIndex": 0, "similarityScore": 0.92, "reason": "candidate 0 directly answers the query"}'

    class FakeProvider:
        name = "twilio"

        async def send_text(self, message, *, settings):
            captured["message"] = message
            captured["settings_provider"] = settings.WHATSAPP_PROVIDER
            return OutboundSendResult(
                provider="twilio",
                accepted=True,
                status="accepted",
                externalMessageId="SM999",
            )

    monkeypatch.setattr("svmp_core.workflows.workflow_b.generate_completion", fake_generate_completion)
    def fake_get_provider(**kwargs):
        captured["requested_provider"] = kwargs.get("requested_provider")
        return FakeProvider()

    monkeypatch.setattr("svmp_core.workflows.workflow_b.get_whatsapp_provider", fake_get_provider)

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

    result = await run_workflow_b(
        database,
        settings=Settings(
            _env_file=None,
            SIMILARITY_THRESHOLD=0.75,
            WHATSAPP_PROVIDER="meta",
            OPENAI_MATCHER_CANDIDATE_LIMIT=8,
        ),
        now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
    )

    assert result.outbound_send_result is not None
    assert result.outbound_send_result.provider == "twilio"
    assert result.outbound_send_result.external_message_id == "SM999"
    assert result.matcher_used == "openai"
    assert captured["requested_provider"] == "twilio"
    assert captured["settings_provider"] == "meta"
    assert captured["message"].tenant_id == "Niyomilan"
    assert captured["message"].client_id == "whatsapp"
    assert captured["message"].user_id == "9845891194"
    assert captured["message"].text == "We help customers."


@pytest.mark.asyncio
async def test_workflow_b_uses_session_provider_for_outbound_routing() -> None:
    """Outbound replies should follow the session provider, not just the global default."""

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

    monkeypatch.setattr("svmp_core.workflows.workflow_b.generate_completion", fake_generate_completion)
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
