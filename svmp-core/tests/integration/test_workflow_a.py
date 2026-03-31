"""Integration-style tests for Workflow A session ingestion."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timedelta, timezone
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
from svmp_core.exceptions import ValidationError
from svmp_core.models import GovernanceLog, KnowledgeEntry, SessionState, WebhookPayload
from svmp_core.workflows import run_workflow_a


class InMemorySessionStateRepository(SessionStateRepository):
    """Small in-memory session repository for workflow tests."""

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
        raise NotImplementedError

    async def delete_stale_sessions(self, before: datetime) -> int:
        raise NotImplementedError


class StubKnowledgeRepository(KnowledgeBaseRepository):
    """Unused stub required by the database contract."""

    async def list_active_by_tenant_and_domain(
        self,
        tenant_id: str,
        domain_id: str,
    ) -> list[KnowledgeEntry]:
        return []


class StubGovernanceRepository(GovernanceLogRepository):
    """Unused stub required by the database contract."""

    async def create(self, log: GovernanceLog) -> GovernanceLog:
        return log


class StubTenantRepository(TenantRepository):
    """Unused stub required by the database contract."""

    async def get_by_tenant_id(self, tenant_id: str) -> Mapping[str, Any] | None:
        return None


class InMemoryDatabase(Database):
    """Small database wrapper for Workflow A tests."""

    def __init__(self) -> None:
        self._session_state = InMemorySessionStateRepository()
        self._knowledge_base = StubKnowledgeRepository()
        self._governance_logs = StubGovernanceRepository()
        self._tenants = StubTenantRepository()

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

    return Settings(_env_file=None, DEBOUNCE_MS=2500)


@pytest.mark.asyncio
async def test_workflow_a_creates_a_new_session_for_first_message() -> None:
    """A first inbound message should create a new open session."""

    database = InMemoryDatabase()
    now = datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc)

    session = await run_workflow_a(
        database,
        WebhookPayload(
            tenantId="Niyomilan",
            clientId="whatsapp",
            userId="9845891194",
            text=" hello ",
        ),
        settings=_settings(),
        now=now,
    )

    assert session.id == "session-1"
    assert session.messages[0].text == "hello"
    assert session.created_at == now
    assert session.updated_at == now
    assert session.debounce_expires_at == now + timedelta(milliseconds=2500)
    assert session.provider == "normalized"
    assert session.processing is False


@pytest.mark.asyncio
async def test_workflow_a_appends_follow_up_message_and_resets_debounce() -> None:
    """A follow-up inbound message should update the existing session."""

    database = InMemoryDatabase()
    first_now = datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc)
    second_now = first_now + timedelta(seconds=4)

    first_session = await run_workflow_a(
        database,
        WebhookPayload(
            tenantId="Niyomilan",
            clientId="whatsapp",
            userId="9845891194",
            text="hi",
        ),
        settings=_settings(),
        now=first_now,
    )

    seeded = await database.session_state.update_by_id(
        first_session.id,
        {"processing": True},
    )
    assert seeded is not None
    assert seeded.processing is True

    updated = await run_workflow_a(
        database,
        WebhookPayload(
            tenantId="Niyomilan",
            clientId="whatsapp",
            userId="9845891194",
            text="what do you do?",
        ),
        settings=_settings(),
        now=second_now,
    )

    assert updated.id == first_session.id
    assert len(updated.messages) == 2
    assert updated.messages[0].text == "hi"
    assert updated.messages[1].text == "what do you do?"
    assert updated.created_at == first_now
    assert updated.updated_at == second_now
    assert updated.debounce_expires_at == second_now + timedelta(milliseconds=2500)
    assert updated.provider == "normalized"
    assert updated.status == "open"
    assert updated.processing is False


@pytest.mark.asyncio
async def test_workflow_a_reopens_existing_identity_session_when_new_input_arrives() -> None:
    """New input should reuse the existing identity session and reopen it for processing."""

    database = InMemoryDatabase()
    first_now = datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc)
    second_now = first_now + timedelta(seconds=4)

    session = await run_workflow_a(
        database,
        WebhookPayload(
            tenantId="Niyomilan",
            clientId="whatsapp",
            userId="9845891194",
            text="hi",
        ),
        settings=_settings(),
        now=first_now,
    )

    seeded = await database.session_state.update_by_id(
        session.id,
        {"status": "closed", "processing": True},
    )
    assert seeded is not None
    assert seeded.status == "closed"
    assert seeded.processing is True

    reopened = await run_workflow_a(
        database,
        WebhookPayload(
            tenantId="Niyomilan",
            clientId="whatsapp",
            userId="9845891194",
            text="what do you do?",
        ),
        settings=_settings(),
        now=second_now,
    )

    assert reopened.id == session.id
    assert reopened.provider == "normalized"
    assert reopened.status == "open"
    assert reopened.processing is False
    assert reopened.messages[-1].text == "what do you do?"


@pytest.mark.asyncio
async def test_workflow_a_rejects_blank_inbound_text() -> None:
    """Blank inbound text should fail safely before touching persistence."""

    database = InMemoryDatabase()

    with pytest.raises(ValidationError, match="inbound text must not be blank"):
        await run_workflow_a(
            database,
            WebhookPayload(
                tenantId="Niyomilan",
                clientId="whatsapp",
                userId="9845891194",
                text="   ",
            ),
            settings=_settings(),
        )


@pytest.mark.asyncio
async def test_workflow_a_rejects_invalid_identity_fields() -> None:
    """Blank identity parts should fail safely before touching persistence."""

    database = InMemoryDatabase()

    with pytest.raises(ValidationError, match="invalid inbound identity"):
        await run_workflow_a(
            database,
            WebhookPayload(
                tenantId="   ",
                clientId="whatsapp",
                userId="9845891194",
                text="hello",
            ),
            settings=_settings(),
        )


@pytest.mark.asyncio
async def test_workflow_a_reuses_legacy_closed_session_for_same_identity() -> None:
    """A new inbound message should reopen a legacy closed session instead of duplicating it."""

    database = InMemoryDatabase()
    first_now = datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc)
    second_now = first_now + timedelta(minutes=5)

    first_session = await run_workflow_a(
        database,
        WebhookPayload(
            tenantId="Niyomilan",
            clientId="whatsapp",
            userId="9845891194",
            text="hi",
        ),
        settings=_settings(),
        now=first_now,
    )

    seeded = await database.session_state.update_by_id(
        first_session.id,
        {"status": "closed", "processing": True},
    )
    assert seeded is not None
    assert seeded.status == "closed"

    updated = await run_workflow_a(
        database,
        WebhookPayload(
            tenantId="Niyomilan",
            clientId="whatsapp",
            userId="9845891194",
            text="back again",
        ),
        settings=_settings(),
        now=second_now,
    )

    assert updated.id == first_session.id
    assert updated.provider == "normalized"
    assert updated.status == "open"
    assert updated.processing is False
    assert [message.text for message in updated.messages] == ["hi", "back again"]


@pytest.mark.asyncio
async def test_workflow_a_updates_provider_from_new_inbound_channel() -> None:
    """New inbound input should refresh the session provider used for outbound replies."""

    database = InMemoryDatabase()
    first_now = datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc)
    second_now = first_now + timedelta(seconds=4)

    first_session = await run_workflow_a(
        database,
        WebhookPayload(
            tenantId="Niyomilan",
            clientId="whatsapp",
            userId="9845891194",
            text="hello from twilio",
            provider="twilio",
        ),
        settings=_settings(),
        now=first_now,
    )

    assert first_session.provider == "twilio"

    updated = await run_workflow_a(
        database,
        WebhookPayload(
            tenantId="Niyomilan",
            clientId="whatsapp",
            userId="9845891194",
            text="hello from meta",
            provider="meta",
        ),
        settings=_settings(),
        now=second_now,
    )

    assert updated.id == first_session.id
    assert updated.provider == "meta"
