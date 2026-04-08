"""Integration-style tests for the onboarding route surface."""

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
from svmp_core.routes.onboarding import build_onboarding_router


class StubSessionStateRepository(SessionStateRepository):
    async def get_by_identity(self, tenant_id: str, client_id: str, user_id: str) -> SessionState | None:
        return None

    async def create(self, session: SessionState) -> SessionState:
        return session

    async def update_by_id(self, session_id: str, data: Mapping[str, Any]) -> SessionState | None:
        return None

    async def acquire_ready_session(self, now):
        return None

    async def delete_stale_sessions(self, before):
        return 0


class StubKnowledgeRepository(KnowledgeBaseRepository):
    async def list_active_by_tenant_and_domain(self, tenant_id: str, domain_id: str) -> list[KnowledgeEntry]:
        return []


class StubGovernanceRepository(GovernanceLogRepository):
    async def create(self, log: GovernanceLog) -> GovernanceLog:
        return log


class InMemoryTenantRepository(TenantRepository):
    def __init__(self) -> None:
        self._documents: dict[str, dict[str, Any]] = {}

    async def get_by_tenant_id(self, tenant_id: str) -> Mapping[str, Any] | None:
        document = self._documents.get(tenant_id)
        return deepcopy(document) if document is not None else None

    async def upsert_tenant(self, tenant_document: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = deepcopy(dict(tenant_document))
        self._documents[str(payload["tenantId"])] = payload
        return deepcopy(payload)


class InMemoryDatabase(Database):
    def __init__(self) -> None:
        self._session_state = StubSessionStateRepository()
        self._knowledge_base = StubKnowledgeRepository()
        self._governance_logs = StubGovernanceRepository()
        self._tenants = InMemoryTenantRepository()

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
    return Settings(
        _env_file=None,
        OPENAI_API_KEY="test-key",
    )


def test_onboarding_post_queues_background_pipeline(monkeypatch) -> None:
    """Onboarding POST should persist a queued tenant onboarding record and return 202."""

    captured: dict[str, Any] = {}

    def fake_launch_background_task(task):
        captured["task"] = task
        task.close()
        return None

    monkeypatch.setattr(
        "svmp_core.routes.onboarding._launch_background_task",
        fake_launch_background_task,
    )

    database = InMemoryDatabase()
    app = FastAPI()
    app.include_router(build_onboarding_router(database, settings=_settings()))

    with TestClient(app) as client:
        response = client.post(
            "/tenants/onboarding",
            json={
                "tenantId": "Stay",
                "websiteUrl": "https://stayparfums.example",
                "brandVoice": "Warm, polished, and premium.",
                "targetFaqCount": 30,
            },
        )

    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "tenantId": "Stay",
        "onboardingStatus": "queued",
        "websiteUrl": "https://stayparfums.example/",
    }
    tenant = database._tenants._documents["Stay"]
    assert tenant["onboarding"]["status"] == "queued"
    assert tenant["brandVoice"] == "Warm, polished, and premium."
    assert "task" in captured


def test_onboarding_status_route_returns_stored_status() -> None:
    """Status GET should expose the tenant's stored onboarding state."""

    database = InMemoryDatabase()
    database._tenants._documents["Stay"] = {
        "tenantId": "Stay",
        "websiteUrl": "https://stayparfums.example/",
        "brandVoice": "Warm, polished, and premium.",
        "updatedAt": "2026-04-08T12:00:00+00:00",
        "onboarding": {
            "status": "completed",
            "generatedFaqCount": 32,
        },
    }

    app = FastAPI()
    app.include_router(build_onboarding_router(database, settings=_settings()))

    with TestClient(app) as client:
        response = client.get("/tenants/Stay/onboarding-status")

    assert response.status_code == 200
    assert response.json()["tenantId"] == "Stay"
    assert response.json()["onboarding"]["status"] == "completed"
    assert response.json()["onboarding"]["generatedFaqCount"] == 32
