"""Integration-style tests for the app factory and scheduler wiring."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

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
from svmp_core.models import GovernanceLog, KnowledgeEntry, SessionState


class InMemorySessionStateRepository(SessionStateRepository):
    """Small session repo so the webhook route can run inside app tests."""

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

    async def acquire_ready_session(self, now):
        return None

    async def acquire_ready_session_by_id(self, session_id, now):
        return None

    async def delete_stale_sessions(self, before):
        return 0


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


class TestDatabase(Database):
    """Database stub with lifecycle flags for app-factory tests."""

    __test__ = False

    def __init__(self) -> None:
        self._session_state = InMemorySessionStateRepository()
        self._knowledge_base = StubKnowledgeRepository()
        self._governance_logs = StubGovernanceRepository()
        self._tenants = StubTenantRepository()
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


class SchedulerStub:
    """Simple scheduler stub that records attached jobs and lifecycle calls."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.running = False
        self.started = False
        self.stopped = False

    def add_job(self, func, trigger: str, id: str, replace_existing: bool, kwargs: dict[str, Any], **schedule):
        self.jobs[id] = {
            "func": func,
            "trigger": trigger,
            "replace_existing": replace_existing,
            "kwargs": kwargs,
            "schedule": schedule,
        }

    def get_job(self, job_id: str):
        return self.jobs.get(job_id)

    def start(self) -> None:
        self.running = True
        self.started = True

    def shutdown(self, wait: bool = False) -> None:
        self.running = False
        self.stopped = True


def _settings() -> Settings:
    """Return deterministic app settings for tests."""

    return Settings(
        _env_file=None,
        APP_NAME="SVMP-Test",
        MONGODB_URI="mongodb://unit-test",
        OPENAI_API_KEY="test-key",
        WHATSAPP_PROVIDER="meta",
        WHATSAPP_TOKEN="test-whatsapp-token",
        WHATSAPP_PHONE_NUMBER_ID="1234567890",
        WHATSAPP_VERIFY_TOKEN="verify-me",
        WORKFLOW_B_INTERVAL_SECONDS=1,
        WORKFLOW_C_INTERVAL_HOURS=24,
    )


def test_create_app_boots_and_wires_lifecycle_dependencies() -> None:
    """The app factory should connect DB, start scheduler, and expose health checks."""

    database = TestDatabase()
    scheduler = SchedulerStub()
    app = create_app(settings=_settings(), database=database, scheduler=scheduler)

    with TestClient(app) as client:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert database.connected is True
        assert scheduler.started is True
        assert "workflow_c" in scheduler.jobs

    assert database.disconnected is True
    assert scheduler.stopped is True


def test_create_app_registers_webhook_route() -> None:
    """The app should expose the webhook verification route after startup."""

    app = create_app(settings=_settings(), database=TestDatabase(), scheduler=SchedulerStub())

    with TestClient(app) as client:
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


def test_create_app_registers_onboarding_route() -> None:
    """The app should expose the tenant onboarding route after startup."""

    app = create_app(settings=_settings(), database=TestDatabase(), scheduler=SchedulerStub())

    with TestClient(app) as client:
        response = client.get("/tenants/missing/onboarding-status")

        assert response.status_code == 404
        assert response.json() == {"detail": "tenant not found"}


def test_create_app_boots_with_twilio_runtime_settings() -> None:
    """Twilio provider settings should also satisfy runtime startup validation."""

    database = TestDatabase()
    scheduler = SchedulerStub()
    app = create_app(
        settings=Settings(
            _env_file=None,
            APP_NAME="SVMP-Twilio-Test",
            MONGODB_URI="mongodb://unit-test",
            OPENAI_API_KEY="test-key",
            WHATSAPP_PROVIDER="twilio",
            TWILIO_ACCOUNT_SID="AC123",
            TWILIO_AUTH_TOKEN="secret",
            TWILIO_WHATSAPP_NUMBER="whatsapp:+14155238886",
            WORKFLOW_B_INTERVAL_SECONDS=1,
            WORKFLOW_C_INTERVAL_HOURS=24,
        ),
        database=database,
        scheduler=scheduler,
    )

    with TestClient(app) as client:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert database.connected is True

    assert database.disconnected is True
