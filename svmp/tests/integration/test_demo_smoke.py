"""End-to-end smoke test for the current Supabase/Vercel-shaped SVMP flow."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from svmp_core.config import Settings
from svmp_core.db.base import (
    Database,
    GovernanceLogRepository,
    KnowledgeBaseRepository,
    SessionStateRepository,
    TenantRepository,
)
from svmp_core.main import create_app
from svmp_core.models import GovernanceDecision, GovernanceLog, KnowledgeEntry, OutboundSendResult, SessionState


class DemoSessionStateRepository(SessionStateRepository):
    """In-memory session repository for the end-to-end smoke flow."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._counter = 0

    async def get_by_identity(
        self,
        tenant_id: str,
        client_id: str,
        user_id: str,
    ) -> SessionState | None:
        for session in self._sessions.values():
            if (
                session.tenant_id == tenant_id
                and session.client_id == client_id
                and session.user_id == user_id
            ):
                return session.model_copy(deep=True)
        return None

    async def create(self, session: SessionState) -> SessionState:
        self._counter += 1
        stored = session.model_copy(update={"id": f"session-{self._counter}"}, deep=True)
        self._sessions[stored.id] = stored
        return stored.model_copy(deep=True)

    async def update_by_id(
        self,
        session_id: str,
        data: Mapping[str, Any],
    ) -> SessionState | None:
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

    async def acquire_ready_session_by_id(self, session_id: str, now: datetime) -> SessionState | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.status != "open" or session.processing is not False or session.debounce_expires_at > now:
            return None
        session.processing = True
        session.updated_at = now
        return session.model_copy(deep=True)

    async def delete_stale_sessions(self, before: datetime) -> int:
        return 0


class DemoKnowledgeRepository(KnowledgeBaseRepository):
    """In-memory knowledge repo for the smoke flow."""

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


class DemoGovernanceRepository(GovernanceLogRepository):
    """Collect governance logs written during the smoke flow."""

    def __init__(self) -> None:
        self.logs: list[GovernanceLog] = []

    async def create(self, log: GovernanceLog) -> GovernanceLog:
        stored = log.model_copy(deep=True)
        self.logs.append(stored)
        return stored


class DemoTenantRepository(TenantRepository):
    """In-memory tenant repo for domain routing and thresholds."""

    def __init__(self, tenants: list[Mapping[str, Any]]) -> None:
        self._tenants = {tenant["tenantId"]: deepcopy(dict(tenant)) for tenant in tenants}

    async def get_by_tenant_id(self, tenant_id: str) -> Mapping[str, Any] | None:
        tenant = self._tenants.get(tenant_id)
        return deepcopy(tenant) if tenant is not None else None


class DemoDatabase(Database):
    """Shared in-memory database used by the app route and Workflow B."""

    def __init__(self) -> None:
        self._session_state = DemoSessionStateRepository()
        self._knowledge_base = DemoKnowledgeRepository(
            [
                KnowledgeEntry(
                    id="faq-1",
                    tenantId="Niyomilan",
                    domainId="general",
                    question="What do you do?",
                    answer="We help customers.",
                )
            ]
        )
        self._governance_logs = DemoGovernanceRepository()
        self._tenants = DemoTenantRepository(
            [
                {
                    "tenantId": "Niyomilan",
                    "domains": [
                        {
                            "domainId": "general",
                            "name": "General",
                            "description": "What we do, company details, and contact information",
                            "keywords": ["what", "company", "contact"],
                        }
                    ],
                    "settings": {"confidenceThreshold": 0.75},
                }
            ]
        )
        self.connected = False
        self.disconnected = False

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
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True


def _settings() -> Settings:
    """Return deterministic runtime settings for the smoke test."""

    return Settings(
        _env_file=None,
        APP_NAME="SVMP-Smoke",
        DATABASE_URL="postgresql://unit-test/postgres",
        OPENAI_API_KEY="test-key",
        WHATSAPP_PROVIDER="normalized",
        ALLOW_NORMALIZED_WEBHOOKS=True,
        DEBOUNCE_MS=0,
        SIMILARITY_THRESHOLD=0.75,
        WORKFLOW_B_MAX_BATCH_SIZE=25,
        WORKFLOW_C_INTERVAL_HOURS=24,
    )


def test_demo_smoke_ingest_then_inline_process_writes_governance_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One inbound webhook should flow through session ingest and inline processing."""

    async def fake_generate_completion(**kwargs) -> str:
        return '{"bestIndex": 0, "similarityScore": 0.92, "reason": "candidate 0 directly answers the query"}'

    async def fake_send_answer_reply(*args, **kwargs) -> OutboundSendResult:
        return OutboundSendResult(
            provider="normalized",
            accepted=True,
            status="accepted",
            externalMessageId="msg-123",
        )

    async def fake_send_typing_indicator_safely(*args, **kwargs) -> dict[str, Any]:
        return {
            "typingIndicatorAttempted": False,
            "typingIndicatorProvider": "normalized",
            "typingIndicatorMessageId": None,
            "typingIndicatorSent": False,
            "typingIndicatorStatus": "skipped",
            "typingIndicatorError": None,
        }

    monkeypatch.setattr("svmp_core.workflows.workflow_b.generate_completion", fake_generate_completion)
    monkeypatch.setattr("svmp_core.workflows.workflow_b._send_answer_reply", fake_send_answer_reply)
    monkeypatch.setattr(
        "svmp_core.workflows.workflow_b._send_typing_indicator_safely",
        fake_send_typing_indicator_safely,
    )

    database = DemoDatabase()
    app = create_app(settings=_settings(), database=database)

    with TestClient(app) as client:
        response = client.post(
            "/webhook",
            json={
                "tenantId": "Niyomilan",
                "clientId": "whatsapp",
                "userId": "9845891194",
                "text": "What do you do?",
            },
        )

        assert response.status_code == 200
        assert response.json() == {
            "status": "accepted",
            "sessionId": "session-1",
        }

    assert database.connected is True
    assert database.disconnected is True

    session = database._session_state._sessions["session-1"]
    assert session.status == "open"
    assert session.processing is True
    assert session.messages == []
    assert session.context == ["What do you do?"]

    written_logs = database.governance_logs.logs
    assert len(written_logs) == 1
    assert written_logs[0].decision == GovernanceDecision.ANSWERED
    assert written_logs[0].combined_text == "What do you do?"
    assert written_logs[0].answer_supplied == "We help customers."
    assert written_logs[0].metadata["matcherUsed"] == "openai"
    assert written_logs[0].metadata["delivery"]["provider"] == "normalized"
    assert written_logs[0].metadata["workflow"] == "workflow_b"
    assert written_logs[0].metadata["decision"] == "answered"
    assert written_logs[0].metadata["sessionId"] == "session-1"
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
    assert isinstance(written_logs[0].metadata["latencyMs"], int)
