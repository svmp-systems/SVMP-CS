"""Integration-style tests for the webhook route surface."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from svmp_core.config import Settings
from svmp_core.db.base import (
    Database,
    GovernanceLogRepository,
    KnowledgeBaseRepository,
    SessionStateRepository,
    TenantRepository,
)
from svmp_core.models import GovernanceLog, KnowledgeEntry, SessionState
from svmp_core.routes import build_webhook_router


class InMemorySessionStateRepository(SessionStateRepository):
    """Small in-memory repository for webhook route tests."""

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
                and session.status == "open"
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

    async def acquire_ready_session(self, now):
        raise NotImplementedError

    async def delete_stale_sessions(self, before):
        raise NotImplementedError


class StubKnowledgeRepository(KnowledgeBaseRepository):
    async def list_active_by_tenant_and_domain(
        self,
        tenant_id: str,
        domain_id: str,
    ) -> list[KnowledgeEntry]:
        return []


class StubGovernanceRepository(GovernanceLogRepository):
    async def create(self, log: GovernanceLog) -> GovernanceLog:
        return log


class StubTenantRepository(TenantRepository):
    async def get_by_tenant_id(self, tenant_id: str) -> Mapping[str, Any] | None:
        return None


class InMemoryDatabase(Database):
    """Small database wrapper for webhook route tests."""

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
    """Return deterministic webhook settings for tests."""

    return Settings(
        _env_file=None,
        DEBOUNCE_MS=2500,
        WHATSAPP_VERIFY_TOKEN="verify-me",
    )


def _build_client() -> TestClient:
    """Build a FastAPI test app with the webhook router attached."""

    app = FastAPI()
    app.include_router(build_webhook_router(InMemoryDatabase(), settings=_settings()))
    return TestClient(app)


def test_webhook_get_verification_returns_challenge() -> None:
    """GET verification should echo the challenge when the token matches."""

    client = _build_client()

    response = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me",
            "hub.challenge": "12345",
        },
    )

    assert response.status_code == 200
    assert response.text == "12345"


def test_webhook_post_intakes_valid_payload() -> None:
    """POST webhook intake should accept already-normalized payloads."""

    client = _build_client()

    response = client.post(
        "/webhook",
        json={
            "tenantId": "Niyomilan",
            "clientId": "whatsapp",
            "userId": "9845891194",
            "text": "hello there",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "accepted",
        "sessionId": "session-1",
    }


def test_webhook_post_rejects_malformed_payload() -> None:
    """Malformed normalized payloads should fail validation at the route boundary."""

    client = _build_client()

    response = client.post(
        "/webhook",
        json={
            "tenantId": "Niyomilan",
            "clientId": "whatsapp",
            "text": "hello there",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "invalid normalized webhook payload"}


def test_webhook_post_normalizes_meta_payload() -> None:
    """Meta webhook JSON should normalize into the internal inbound schema."""

    client = _build_client()

    response = client.post(
        "/webhook",
        headers={"X-SVMP-Tenant-Id": "Niyomilan", "X-SVMP-Provider": "meta"},
        json={
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "id": "wamid.HBgM123",
                                        "from": "919845891194",
                                        "text": {"body": "hello from meta"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "accepted",
        "sessionId": "session-1",
    }


def test_webhook_post_normalizes_twilio_form_payload() -> None:
    """Twilio form posts should normalize into the internal inbound schema."""

    client = _build_client()

    response = client.post(
        "/webhook",
        headers={"X-SVMP-Tenant-Id": "Niyomilan", "X-SVMP-Provider": "twilio"},
        data={
            "MessageSid": "SM123",
            "From": "whatsapp:+919845891194",
            "Body": "hello from twilio",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "accepted",
        "sessionId": "session-1",
    }


def test_webhook_post_rejects_provider_payload_without_tenant() -> None:
    """Provider-native payloads should require an explicit tenant identity."""

    client = _build_client()

    response = client.post(
        "/webhook",
        headers={"X-SVMP-Provider": "twilio"},
        data={
            "MessageSid": "SM123",
            "From": "whatsapp:+919845891194",
            "Body": "hello from twilio",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "tenantId is required"}


def test_webhook_get_returns_405_for_twilio_provider() -> None:
    """GET verification should only work for providers that support it."""

    client = _build_client()

    response = client.get(
        "/webhook",
        params={"provider": "twilio"},
    )

    assert response.status_code == 405
    assert response.json() == {
        "detail": "webhook verification is not supported for provider: twilio"
    }
