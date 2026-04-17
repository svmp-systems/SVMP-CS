"""Integration-style tests for the app factory and scheduler wiring."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from svmp_core.config import Settings
from svmp_core.db.base import (
    AuditLogRepository,
    Database,
    GovernanceLogRepository,
    KnowledgeBaseRepository,
    SessionStateRepository,
    TenantRepository,
)
from svmp_core.main import create_app
from svmp_core.models import GovernanceDecision, GovernanceLog, KnowledgeEntry, MessageItem, SessionState


class InMemorySessionStateRepository(SessionStateRepository):
    """Small session repo so the webhook route can run inside app tests."""

    def __init__(self, sessions: list[SessionState] | None = None) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._counter = 0
        for session in sessions or []:
            if session.id is not None:
                self._sessions[session.id] = session.model_copy(deep=True)

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

    async def delete_stale_sessions(self, before):
        return 0

    async def list_by_tenant(
        self,
        tenant_id: str,
        *,
        limit: int = 50,
    ) -> list[SessionState]:
        sessions = [
            session.model_copy(deep=True)
            for session in self._sessions.values()
            if session.tenant_id == tenant_id
        ]
        return sorted(sessions, key=lambda session: session.updated_at, reverse=True)[:limit]


class StubKnowledgeRepository(KnowledgeBaseRepository):
    def __init__(self, entries: list[KnowledgeEntry] | None = None) -> None:
        self._entries = [entry.model_copy(deep=True) for entry in entries or []]

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

    async def list_by_tenant(
        self,
        tenant_id: str,
        *,
        active: bool | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[KnowledgeEntry]:
        entries = [entry for entry in self._entries if entry.tenant_id == tenant_id]
        if active is not None:
            entries = [entry for entry in entries if entry.active is active]
        if search:
            normalized = search.lower()
            entries = [
                entry
                for entry in entries
                if normalized in entry.question.lower()
                or normalized in entry.answer.lower()
                or normalized in entry.domain_id.lower()
                or any(normalized in tag.lower() for tag in entry.tags)
            ]
        return [entry.model_copy(deep=True) for entry in entries[:limit]]

    async def create(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        stored = entry.model_copy(
            update={"id": entry.id or f"faq-{len(self._entries) + 1}"},
            deep=True,
        )
        self._entries.append(stored)
        return stored.model_copy(deep=True)

    async def update_by_id(
        self,
        tenant_id: str,
        entry_id: str,
        data: Mapping[str, Any],
    ) -> KnowledgeEntry | None:
        for index, entry in enumerate(self._entries):
            if entry.tenant_id != tenant_id or entry.id != entry_id:
                continue
            updated = entry.model_copy(update=deepcopy(dict(data)), deep=True)
            self._entries[index] = updated
            return updated.model_copy(deep=True)
        return None

    async def deactivate_by_id(
        self,
        tenant_id: str,
        entry_id: str,
        data: Mapping[str, Any],
    ) -> KnowledgeEntry | None:
        return await self.update_by_id(
            tenant_id,
            entry_id,
            {
                **dict(data),
                "active": False,
            },
        )


class StubGovernanceRepository(GovernanceLogRepository):
    def __init__(self, logs: list[GovernanceLog] | None = None) -> None:
        self._logs = [log.model_copy(deep=True) for log in logs or []]

    async def create(self, log: GovernanceLog) -> GovernanceLog:
        self._logs.append(log.model_copy(deep=True))
        return log

    async def list_by_tenant(
        self,
        tenant_id: str,
        *,
        limit: int = 100,
    ) -> list[GovernanceLog]:
        logs = [
            log.model_copy(deep=True)
            for log in self._logs
            if log.tenant_id == tenant_id
        ]
        return sorted(logs, key=lambda log: log.timestamp, reverse=True)[:limit]

    async def count_by_decision(self, tenant_id: str) -> Mapping[str, int]:
        counts: dict[str, int] = {}
        for log in self._logs:
            if log.tenant_id != tenant_id:
                continue
            counts[log.decision.value] = counts.get(log.decision.value, 0) + 1
        return counts


class StubTenantRepository(TenantRepository):
    def __init__(
        self,
        dashboard_context: Mapping[str, Any] | None = None,
        tenant_document: Mapping[str, Any] | None = None,
        integrations: list[Mapping[str, Any]] | None = None,
    ) -> None:
        self._dashboard_context = deepcopy(dict(dashboard_context)) if dashboard_context else None
        self._tenant_document = deepcopy(dict(tenant_document)) if tenant_document else None
        self._integrations = [deepcopy(dict(item)) for item in integrations or []]

    async def get_by_tenant_id(self, tenant_id: str) -> Mapping[str, Any] | None:
        if self._tenant_document and self._tenant_document.get("tenantId") == tenant_id:
            return deepcopy(self._tenant_document)
        return None

    async def resolve_dashboard_tenant_context(
        self,
        *,
        clerk_organization_id: str,
        clerk_user_id: str,
    ) -> Mapping[str, Any] | None:
        return deepcopy(self._dashboard_context) if self._dashboard_context else None

    async def list_integration_status(
        self,
        tenant_id: str,
    ) -> list[Mapping[str, Any]]:
        return [
            deepcopy(item)
            for item in self._integrations
            if item.get("tenantId") == tenant_id
        ]

    async def update_by_tenant_id(
        self,
        tenant_id: str,
        data: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        if self._tenant_document is None or self._tenant_document.get("tenantId") != tenant_id:
            return None
        for key, value in data.items():
            if "." not in key:
                self._tenant_document[key] = deepcopy(value)
                continue
            current = self._tenant_document
            parts = key.split(".")
            for part in parts[:-1]:
                nested = current.get(part)
                if not isinstance(nested, dict):
                    nested = {}
                    current[part] = nested
                current = nested
            current[parts[-1]] = deepcopy(value)
        return deepcopy(self._tenant_document)

    async def update_integration_status(
        self,
        tenant_id: str,
        provider: str,
        data: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        for index, integration in enumerate(self._integrations):
            if integration.get("tenantId") == tenant_id and integration.get("provider") == provider:
                updated = {
                    **integration,
                    **deepcopy(dict(data)),
                    "tenantId": tenant_id,
                    "provider": provider,
                }
                self._integrations[index] = updated
                return deepcopy(updated)
        created = {
            **deepcopy(dict(data)),
            "tenantId": tenant_id,
            "provider": provider,
        }
        self._integrations.append(created)
        return deepcopy(created)


class StubAuditRepository(AuditLogRepository):
    def __init__(self) -> None:
        self.logs: list[Mapping[str, Any]] = []

    async def create(self, log: Mapping[str, Any]) -> Mapping[str, Any]:
        stored = deepcopy(dict(log))
        self.logs.append(stored)
        return stored


class TestDatabase(Database):
    """Database stub with lifecycle flags for app-factory tests."""

    __test__ = False

    def __init__(
        self,
        *,
        tenant_repo: TenantRepository | None = None,
        session_repo: SessionStateRepository | None = None,
        knowledge_repo: KnowledgeBaseRepository | None = None,
        governance_repo: GovernanceLogRepository | None = None,
        audit_repo: AuditLogRepository | None = None,
    ) -> None:
        self._session_state = session_repo or InMemorySessionStateRepository()
        self._knowledge_base = knowledge_repo or StubKnowledgeRepository()
        self._governance_logs = governance_repo or StubGovernanceRepository()
        self._tenants = tenant_repo or StubTenantRepository()
        self._audit_logs = audit_repo or StubAuditRepository()
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

    @property
    def audit_logs(self) -> AuditLogRepository:
        return self._audit_logs

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
        META_APP_SECRET="app-secret",
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
        assert "workflow_b" in scheduler.jobs
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


def test_dashboard_me_requires_enabled_dashboard_auth() -> None:
    """Dashboard APIs should reject requests when dashboard auth is disabled."""

    app = create_app(settings=_settings(), database=TestDatabase(), scheduler=SchedulerStub())

    with TestClient(app) as client:
        response = client.get("/api/me")

        assert response.status_code == 401
        assert response.json()["detail"] == "dashboard authentication is disabled"


def test_dashboard_me_resolves_tenant_context_from_backend_membership() -> None:
    """The browser must not be able to choose the tenant boundary."""

    database = TestDatabase(
        tenant_repo=StubTenantRepository(
            {
                "tenantId": "stay",
                "tenantName": "Stay Parfums",
                "role": "admin",
                "subscriptionStatus": "active",
            }
        )
    )
    app = create_app(
        settings=Settings(
            _env_file=None,
            APP_NAME="SVMP-Dashboard-Test",
            MONGODB_URI="mongodb://unit-test",
            OPENAI_API_KEY="test-key",
            WHATSAPP_PROVIDER="meta",
            WHATSAPP_TOKEN="test-whatsapp-token",
            WHATSAPP_PHONE_NUMBER_ID="1234567890",
            WHATSAPP_VERIFY_TOKEN="verify-me",
            META_APP_SECRET="app-secret",
            DASHBOARD_AUTH_MODE="trusted_headers",
            WORKFLOW_B_INTERVAL_SECONDS=1,
            WORKFLOW_C_INTERVAL_HOURS=24,
        ),
        database=database,
        scheduler=SchedulerStub(),
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/me",
            params={"tenantId": "evil"},
            headers={
                "X-SVMP-User-Id": "user_123",
                "X-SVMP-Organization-Id": "org_123",
                "X-SVMP-User-Email": "admin@stayparfums.com",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["tenantId"] == "stay"
        assert body["tenantName"] == "Stay Parfums"
        assert body["role"] == "admin"
        assert body["subscriptionStatus"] == "active"
        assert body["hasActiveSubscription"] is True
        assert "knowledge_base.manage" in body["allowedActions"]
        assert "billing.manage" not in body["allowedActions"]


def test_dashboard_me_limits_inactive_subscription_to_billing_actions() -> None:
    """Inactive tenants should only receive billing recovery actions from /api/me."""

    database = TestDatabase(
        tenant_repo=StubTenantRepository(
            {
                "tenantId": "stay",
                "tenantName": "Stay Parfums",
                "role": "owner",
                "subscriptionStatus": "past_due",
            }
        )
    )
    app = create_app(
        settings=Settings(
            _env_file=None,
            APP_NAME="SVMP-Dashboard-Billing-Test",
            MONGODB_URI="mongodb://unit-test",
            OPENAI_API_KEY="test-key",
            WHATSAPP_PROVIDER="meta",
            WHATSAPP_TOKEN="test-whatsapp-token",
            WHATSAPP_PHONE_NUMBER_ID="1234567890",
            WHATSAPP_VERIFY_TOKEN="verify-me",
            META_APP_SECRET="app-secret",
            DASHBOARD_AUTH_MODE="trusted_headers",
            WORKFLOW_B_INTERVAL_SECONDS=1,
            WORKFLOW_C_INTERVAL_HOURS=24,
        ),
        database=database,
        scheduler=SchedulerStub(),
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/me",
            headers={
                "X-SVMP-User-Id": "user_123",
                "X-SVMP-Organization-Id": "org_123",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["hasActiveSubscription"] is False
        assert body["allowedActions"] == [
            "billing.read",
            "billing.checkout",
            "billing.portal",
        ]


def test_dashboard_read_endpoints_return_resolved_tenant_data() -> None:
    """Dashboard read APIs should use the resolved tenant for every query."""

    now = datetime(2026, 4, 17, 8, 0, tzinfo=timezone.utc)
    tenant_repo = StubTenantRepository(
        {
            "tenantId": "stay",
            "tenantName": "Stay Parfums",
            "role": "owner",
            "subscriptionStatus": "active",
        },
        tenant_document={
            "tenantId": "stay",
            "tenantName": "Stay Parfums",
            "websiteUrl": "https://stayparfums.com",
            "industry": "Fragrance",
            "supportEmail": "support@stayparfums.com",
            "brandVoice": {
                "tone": "Warm, polished, premium",
                "use": ["concise"],
                "avoid": ["overpromising"],
            },
            "settings": {"confidenceThreshold": 0.75},
        },
        integrations=[
            {
                "tenantId": "stay",
                "provider": "whatsapp",
                "status": "connected",
                "health": "healthy",
                "accessToken": "secret-token",
            }
        ],
    )
    database = TestDatabase(
        tenant_repo=tenant_repo,
        session_repo=InMemorySessionStateRepository(
            [
                SessionState(
                    _id="session-1",
                    tenantId="stay",
                    clientId="whatsapp",
                    userId="9845891194",
                    provider="meta",
                    messages=[MessageItem(text="Do you have free shipping?", at=now)],
                    createdAt=now,
                    updatedAt=now,
                    debounceExpiresAt=now,
                )
            ]
        ),
        knowledge_repo=StubKnowledgeRepository(
            [
                KnowledgeEntry(
                    _id="faq-shipping",
                    tenantId="stay",
                    domainId="general",
                    question="Do you have free shipping?",
                    answer="Yes, shipping is free.",
                    tags=["shipping"],
                    active=True,
                )
            ]
        ),
        governance_repo=StubGovernanceRepository(
            [
                GovernanceLog(
                    _id="log-1",
                    tenantId="stay",
                    clientId="whatsapp",
                    userId="9845891194",
                    decision=GovernanceDecision.ANSWERED,
                    similarityScore=0.92,
                    combinedText="Do you have free shipping?",
                    answerSupplied="Yes, shipping is free.",
                    timestamp=now,
                    metadata={"matchedQuestion": "Do you have free shipping?"},
                )
            ]
        ),
    )
    app = create_app(
        settings=Settings(
            _env_file=None,
            APP_NAME="SVMP-Dashboard-Read-Test",
            MONGODB_URI="mongodb://unit-test",
            OPENAI_API_KEY="test-key",
            WHATSAPP_PROVIDER="meta",
            WHATSAPP_TOKEN="test-whatsapp-token",
            WHATSAPP_PHONE_NUMBER_ID="1234567890",
            WHATSAPP_VERIFY_TOKEN="verify-me",
            META_APP_SECRET="app-secret",
            DASHBOARD_AUTH_MODE="trusted_headers",
            WORKFLOW_B_INTERVAL_SECONDS=1,
            WORKFLOW_C_INTERVAL_HOURS=24,
        ),
        database=database,
        scheduler=SchedulerStub(),
    )
    headers = {
        "X-SVMP-User-Id": "user_123",
        "X-SVMP-Organization-Id": "org_123",
    }

    with TestClient(app) as client:
        tenant_response = client.get("/api/tenant", params={"tenantId": "evil"}, headers=headers)
        overview_response = client.get("/api/overview", headers=headers)
        sessions_response = client.get("/api/sessions", headers=headers)
        kb_response = client.get("/api/knowledge-base", params={"search": "shipping"}, headers=headers)
        brand_response = client.get("/api/brand-voice", headers=headers)
        governance_response = client.get("/api/governance", headers=headers)
        integrations_response = client.get("/api/integrations", headers=headers)

        assert tenant_response.status_code == 200
        assert tenant_response.json()["tenantId"] == "stay"
        assert tenant_response.json()["supportEmail"] == "support@stayparfums.com"

        assert overview_response.status_code == 200
        assert overview_response.json()["metrics"]["aiResolved"] == 1
        assert overview_response.json()["metrics"]["deflectionRate"] == 1.0

        assert sessions_response.status_code == 200
        assert sessions_response.json()["sessions"][0]["tenantId"] == "stay"
        assert sessions_response.json()["sessions"][0]["latestMessage"] == "Do you have free shipping?"

        assert kb_response.status_code == 200
        assert kb_response.json()["entries"][0]["_id"] == "faq-shipping"

        assert brand_response.status_code == 200
        assert brand_response.json()["brandVoice"]["tone"] == "Warm, polished, premium"

        assert governance_response.status_code == 200
        assert governance_response.json()["logs"][0]["decision"] == "answered"

        assert integrations_response.status_code == 200
        whatsapp = integrations_response.json()["integrations"][0]
        assert whatsapp["provider"] == "whatsapp"
        assert whatsapp["accessToken"] == "[redacted]"


def test_dashboard_operational_reads_require_active_subscription() -> None:
    """Operational dashboard endpoints should be blocked for inactive tenants."""

    database = TestDatabase(
        tenant_repo=StubTenantRepository(
            {
                "tenantId": "stay",
                "tenantName": "Stay Parfums",
                "role": "owner",
                "subscriptionStatus": "past_due",
            }
        )
    )
    app = create_app(
        settings=Settings(
            _env_file=None,
            APP_NAME="SVMP-Dashboard-Inactive-Test",
            MONGODB_URI="mongodb://unit-test",
            OPENAI_API_KEY="test-key",
            WHATSAPP_PROVIDER="meta",
            WHATSAPP_TOKEN="test-whatsapp-token",
            WHATSAPP_PHONE_NUMBER_ID="1234567890",
            WHATSAPP_VERIFY_TOKEN="verify-me",
            META_APP_SECRET="app-secret",
            DASHBOARD_AUTH_MODE="trusted_headers",
            WORKFLOW_B_INTERVAL_SECONDS=1,
            WORKFLOW_C_INTERVAL_HOURS=24,
        ),
        database=database,
        scheduler=SchedulerStub(),
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/overview",
            headers={
                "X-SVMP-User-Id": "user_123",
                "X-SVMP-Organization-Id": "org_123",
            },
        )

        assert response.status_code == 402
        assert response.json()["detail"] == "active subscription required"


def test_dashboard_write_endpoints_enforce_roles_and_write_audit_logs() -> None:
    """Owner/admin dashboard writes should mutate tenant data and create audit logs."""

    audit_repo = StubAuditRepository()
    knowledge_repo = StubKnowledgeRepository(
        [
            KnowledgeEntry(
                _id="faq-shipping",
                tenantId="stay",
                domainId="general",
                question="Do you have free shipping?",
                answer="Yes, shipping is free.",
                tags=["shipping"],
                active=True,
            )
        ]
    )
    database = TestDatabase(
        tenant_repo=StubTenantRepository(
            {
                "tenantId": "stay",
                "tenantName": "Stay Parfums",
                "role": "owner",
                "subscriptionStatus": "active",
            },
            tenant_document={
                "tenantId": "stay",
                "tenantName": "Stay Parfums",
                "brandVoice": {"tone": "Warm"},
                "settings": {"confidenceThreshold": 0.75},
            },
        ),
        knowledge_repo=knowledge_repo,
        audit_repo=audit_repo,
    )
    app = create_app(
        settings=Settings(
            _env_file=None,
            APP_NAME="SVMP-Dashboard-Write-Test",
            MONGODB_URI="mongodb://unit-test",
            OPENAI_API_KEY="test-key",
            WHATSAPP_PROVIDER="meta",
            WHATSAPP_TOKEN="test-whatsapp-token",
            WHATSAPP_PHONE_NUMBER_ID="1234567890",
            WHATSAPP_VERIFY_TOKEN="verify-me",
            META_APP_SECRET="app-secret",
            DASHBOARD_AUTH_MODE="trusted_headers",
            WORKFLOW_B_INTERVAL_SECONDS=1,
            WORKFLOW_C_INTERVAL_HOURS=24,
        ),
        database=database,
        scheduler=SchedulerStub(),
    )
    headers = {
        "X-SVMP-User-Id": "owner_123",
        "X-SVMP-Organization-Id": "org_123",
        "X-SVMP-User-Email": "owner@stayparfums.com",
    }

    with TestClient(app) as client:
        tenant_response = client.patch(
            "/api/tenant",
            json={
                "tenantName": "Stay Parfums India",
                "settings": {"confidenceThreshold": 0.82, "ignoredSetting": True},
            },
            headers=headers,
        )
        brand_response = client.patch(
            "/api/brand-voice",
            json={"tone": "Warm, polished", "avoid": ["overpromising"]},
            headers=headers,
        )
        create_response = client.post(
            "/api/knowledge-base",
            json={
                "domainId": "general",
                "question": "What is the pair offer?",
                "answer": "Any two eligible fragrances are available in the pair offer.",
                "tags": ["offer"],
                "active": True,
            },
            headers=headers,
        )
        update_response = client.patch(
            "/api/knowledge-base/faq-shipping",
            json={"answer": "Yes, shipping is free on all orders."},
            headers=headers,
        )
        delete_response = client.delete(
            "/api/knowledge-base/faq-shipping",
            headers=headers,
        )
        integration_response = client.patch(
            "/api/integrations/whatsapp",
            json={"status": "connected", "health": "healthy"},
            headers=headers,
        )

        assert tenant_response.status_code == 200
        assert tenant_response.json()["tenantName"] == "Stay Parfums India"
        assert tenant_response.json()["settings"]["confidenceThreshold"] == 0.82
        assert "ignoredSetting" not in tenant_response.json()["settings"]

        assert brand_response.status_code == 200
        assert brand_response.json()["brandVoice"]["tone"] == "Warm, polished"
        assert brand_response.json()["brandVoice"]["avoid"] == ["overpromising"]

        assert create_response.status_code == 201
        assert create_response.json()["tenantId"] == "stay"
        assert create_response.json()["question"] == "What is the pair offer?"

        assert update_response.status_code == 200
        assert update_response.json()["answer"] == "Yes, shipping is free on all orders."

        assert delete_response.status_code == 200
        assert delete_response.json()["active"] is False

        assert integration_response.status_code == 200
        assert integration_response.json()["provider"] == "whatsapp"
        assert integration_response.json()["status"] == "connected"

    assert [
        log["action"]
        for log in audit_repo.logs
    ] == [
        "tenant.updated",
        "brand_voice.updated",
        "knowledge_base.created",
        "knowledge_base.updated",
        "knowledge_base.deactivated",
        "integration.whatsapp.updated",
    ]
    assert all(log["tenantId"] == "stay" for log in audit_repo.logs)


def test_dashboard_write_endpoints_reject_analyst_and_integration_secrets() -> None:
    """Only owner/admin may write, and integration status cannot carry secrets."""

    database = TestDatabase(
        tenant_repo=StubTenantRepository(
            {
                "tenantId": "stay",
                "tenantName": "Stay Parfums",
                "role": "analyst",
                "subscriptionStatus": "active",
            },
            tenant_document={"tenantId": "stay", "tenantName": "Stay Parfums"},
        )
    )
    app = create_app(
        settings=Settings(
            _env_file=None,
            APP_NAME="SVMP-Dashboard-Write-Role-Test",
            MONGODB_URI="mongodb://unit-test",
            OPENAI_API_KEY="test-key",
            WHATSAPP_PROVIDER="meta",
            WHATSAPP_TOKEN="test-whatsapp-token",
            WHATSAPP_PHONE_NUMBER_ID="1234567890",
            WHATSAPP_VERIFY_TOKEN="verify-me",
            META_APP_SECRET="app-secret",
            DASHBOARD_AUTH_MODE="trusted_headers",
            WORKFLOW_B_INTERVAL_SECONDS=1,
            WORKFLOW_C_INTERVAL_HOURS=24,
        ),
        database=database,
        scheduler=SchedulerStub(),
    )

    with TestClient(app) as client:
        role_response = client.patch(
            "/api/brand-voice",
            json={"tone": "Warm"},
            headers={
                "X-SVMP-User-Id": "analyst_123",
                "X-SVMP-Organization-Id": "org_123",
            },
        )

    assert role_response.status_code == 403

    owner_database = TestDatabase(
        tenant_repo=StubTenantRepository(
            {
                "tenantId": "stay",
                "tenantName": "Stay Parfums",
                "role": "owner",
                "subscriptionStatus": "active",
            },
            tenant_document={"tenantId": "stay", "tenantName": "Stay Parfums"},
        )
    )
    owner_app = create_app(
        settings=Settings(
            _env_file=None,
            APP_NAME="SVMP-Dashboard-Secret-Test",
            MONGODB_URI="mongodb://unit-test",
            OPENAI_API_KEY="test-key",
            WHATSAPP_PROVIDER="meta",
            WHATSAPP_TOKEN="test-whatsapp-token",
            WHATSAPP_PHONE_NUMBER_ID="1234567890",
            WHATSAPP_VERIFY_TOKEN="verify-me",
            META_APP_SECRET="app-secret",
            DASHBOARD_AUTH_MODE="trusted_headers",
            WORKFLOW_B_INTERVAL_SECONDS=1,
            WORKFLOW_C_INTERVAL_HOURS=24,
        ),
        database=owner_database,
        scheduler=SchedulerStub(),
    )

    with TestClient(owner_app) as client:
        secret_response = client.patch(
            "/api/integrations/whatsapp",
            json={"metadata": {"accessToken": "do-not-store-here"}},
            headers={
                "X-SVMP-User-Id": "owner_123",
                "X-SVMP-Organization-Id": "org_123",
            },
        )

    assert secret_response.status_code == 400
    assert secret_response.json()["detail"] == "integration secrets must not be submitted to this endpoint"
