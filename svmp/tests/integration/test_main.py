"""Integration-style tests for app wiring, dashboard APIs, billing, and internal jobs."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from svmp_core.config import Settings
from svmp_core.db.base import (
    AuditLogRepository,
    BillingSubscriptionRepository,
    Database,
    GovernanceLogRepository,
    KnowledgeBaseRepository,
    ProviderEventRepository,
    SessionStateRepository,
    TenantRepository,
)
from svmp_core.main import create_app
from svmp_core.models import GovernanceDecision, GovernanceLog, KnowledgeEntry, MessageItem, SessionState


class InMemorySessionStateRepository(SessionStateRepository):
    """Small session repo so app routes can run inside integration tests."""

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

    async def acquire_ready_session_by_id(self, session_id, now):
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

    async def get_by_id(
        self,
        tenant_id: str,
        session_id: str,
    ) -> SessionState | None:
        session = self._sessions.get(session_id)
        if session is None or session.tenant_id != tenant_id:
            return None
        return session.model_copy(deep=True)


class StubKnowledgeRepository(KnowledgeBaseRepository):
    """Knowledge-base repository with dashboard-friendly read and write helpers."""

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
    """Governance repository with list and aggregation support."""

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
    """Tenant repository for dashboard resolution, profile reads, and integration updates."""

    def __init__(
        self,
        dashboard_context: Mapping[str, Any] | None = None,
        tenant_document: Mapping[str, Any] | None = None,
        integrations: list[Mapping[str, Any]] | None = None,
    ) -> None:
        self._dashboard_context = deepcopy(dict(dashboard_context)) if dashboard_context else None
        self._tenant_document = deepcopy(dict(tenant_document)) if tenant_document else None
        self._integrations = [deepcopy(dict(item)) for item in integrations or []]
        self.last_resolve_kwargs: dict[str, Any] | None = None

    async def get_by_tenant_id(self, tenant_id: str) -> Mapping[str, Any] | None:
        if self._tenant_document and self._tenant_document.get("tenantId") == tenant_id:
            return deepcopy(self._tenant_document)
        return None

    async def resolve_dashboard_tenant_context(
        self,
        *,
        auth_provider: str = "supabase",
        provider_user_id: str | None = None,
        email: str | None = None,
        organization_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        self.last_resolve_kwargs = {
            "auth_provider": auth_provider,
            "provider_user_id": provider_user_id,
            "email": email,
            "organization_id": organization_id,
        }
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
    """Audit repository that captures dashboard writes."""

    def __init__(self) -> None:
        self.logs: list[Mapping[str, Any]] = []

    async def create(self, log: Mapping[str, Any]) -> Mapping[str, Any]:
        stored = deepcopy(dict(log))
        self.logs.append(stored)
        return stored


class StubBillingRepository(BillingSubscriptionRepository):
    """Billing repository keyed by tenant id."""

    def __init__(self, records: list[Mapping[str, Any]] | None = None) -> None:
        self.records = {
            str(record["tenantId"]): deepcopy(dict(record))
            for record in records or []
            if "tenantId" in record
        }

    async def get_by_tenant_id(self, tenant_id: str) -> Mapping[str, Any] | None:
        record = self.records.get(tenant_id)
        return deepcopy(record) if record else None

    async def upsert_by_tenant_id(
        self,
        tenant_id: str,
        data: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        current = self.records.get(tenant_id, {"tenantId": tenant_id})
        updated = {**current, **deepcopy(dict(data)), "tenantId": tenant_id}
        self.records[tenant_id] = updated
        return deepcopy(updated)

    async def get_by_stripe_ids(
        self,
        *,
        stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        for record in self.records.values():
            if stripe_subscription_id and record.get("stripeSubscriptionId") == stripe_subscription_id:
                return deepcopy(record)
            if stripe_customer_id and record.get("stripeCustomerId") == stripe_customer_id:
                return deepcopy(record)
        return None


class StubProviderEventRepository(ProviderEventRepository):
    """Provider-event repository with idempotent recording."""

    def __init__(self) -> None:
        self.events: set[tuple[str, str]] = set()

    async def record_once(
        self,
        *,
        provider: str,
        event_id: str,
        event_type: str,
        tenant_id: str | None,
        payload_hash: str,
    ) -> bool:
        key = (provider, event_id)
        if key in self.events:
            return False
        self.events.add(key)
        return True


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
        billing_repo: BillingSubscriptionRepository | None = None,
        provider_events_repo: ProviderEventRepository | None = None,
    ) -> None:
        self._session_state = session_repo or InMemorySessionStateRepository()
        self._knowledge_base = knowledge_repo or StubKnowledgeRepository()
        self._governance_logs = governance_repo or StubGovernanceRepository()
        self._tenants = tenant_repo or StubTenantRepository()
        self._audit_logs = audit_repo or StubAuditRepository()
        self._billing_subscriptions = billing_repo or StubBillingRepository()
        self._provider_events = provider_events_repo or StubProviderEventRepository()
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

    @property
    def billing_subscriptions(self) -> BillingSubscriptionRepository:
        return self._billing_subscriptions

    @property
    def provider_events(self) -> ProviderEventRepository:
        return self._provider_events

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True


def _settings(**overrides: Any) -> Settings:
    """Return deterministic app settings for tests."""

    base = {
        "_env_file": None,
        "APP_NAME": "SVMP-Test",
        "DATABASE_URL": "postgresql://unit-test/postgres",
        "OPENAI_API_KEY": "test-key",
        "WHATSAPP_PROVIDER": "normalized",
        "ALLOW_NORMALIZED_WEBHOOKS": True,
        "DEBOUNCE_MS": 0,
        "WORKFLOW_B_MAX_BATCH_SIZE": 25,
        "WORKFLOW_C_INTERVAL_HOURS": 24,
    }
    base.update(overrides)
    return Settings(**base)


def _trusted_headers(
    *,
    user_id: str = "user_123",
    organization_id: str = "org_123",
    email: str | None = "owner@stayparfums.com",
) -> dict[str, str]:
    """Return trusted dashboard auth headers for integration tests."""

    headers = {
        "X-SVMP-User-Id": user_id,
        "X-SVMP-Organization-Id": organization_id,
    }
    if email is not None:
        headers["X-SVMP-User-Email"] = email
    return headers


def _stripe_signature(raw_body: bytes, secret: str) -> str:
    """Build a valid Stripe test signature."""

    timestamp = int(datetime.now(timezone.utc).timestamp())
    signed_payload = str(timestamp).encode("utf-8") + b"." + raw_body
    signature = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def test_create_app_boots_and_exposes_health() -> None:
    """The app factory should connect the database and expose health checks."""

    database = TestDatabase()
    app = create_app(settings=_settings(), database=database)

    with TestClient(app) as client:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert database.connected is True

    assert database.disconnected is True


def test_dashboard_me_requires_enabled_dashboard_auth() -> None:
    """Dashboard APIs should reject requests when dashboard auth is disabled."""

    app = create_app(settings=_settings(), database=TestDatabase())

    with TestClient(app) as client:
        response = client.get("/api/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "dashboard authentication is disabled"


def test_dashboard_me_resolves_tenant_context_from_backend_membership() -> None:
    """The browser must not be able to choose the tenant boundary."""

    tenant_repo = StubTenantRepository(
        {
            "tenantId": "stay",
            "tenantName": "Stay Parfums",
            "role": "admin",
            "subscriptionStatus": "active",
        }
    )
    database = TestDatabase(tenant_repo=tenant_repo)
    app = create_app(
        settings=_settings(DASHBOARD_AUTH_MODE="trusted_headers"),
        database=database,
    )

    with TestClient(app) as client:
        response = client.get("/api/me", headers=_trusted_headers())

    assert response.status_code == 200
    assert response.json()["tenantId"] == "stay"
    assert response.json()["role"] == "admin"
    assert response.json()["hasActiveSubscription"] is True
    assert "knowledge_base.manage" in response.json()["allowedActions"]
    assert tenant_repo.last_resolve_kwargs == {
        "auth_provider": "trusted_headers",
        "provider_user_id": "user_123",
        "email": "owner@stayparfums.com",
        "organization_id": "org_123",
    }


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
        settings=_settings(DASHBOARD_AUTH_MODE="trusted_headers"),
        database=database,
    )

    with TestClient(app) as client:
        response = client.get("/api/overview", headers=_trusted_headers())

    assert response.status_code == 402
    assert response.json()["detail"] == "active subscription required"


def test_dashboard_operational_reads_return_expected_payloads() -> None:
    """Dashboard reads should return current tenant-scoped data and redacted integrations."""

    session_repo = InMemorySessionStateRepository(
        [
            SessionState(
                id="session-1",
                tenantId="stay",
                clientId="whatsapp",
                userId="919845891194",
                provider="meta",
                status="open",
                processing=False,
                context=["Customer asked about fragrances."],
                messages=[MessageItem(text="Do you have free shipping?")],
                createdAt=datetime(2026, 4, 25, 9, 0, tzinfo=timezone.utc),
                updatedAt=datetime(2026, 4, 25, 9, 5, tzinfo=timezone.utc),
                debounceExpiresAt=datetime(2026, 4, 25, 9, 5, tzinfo=timezone.utc),
            )
        ]
    )
    knowledge_repo = StubKnowledgeRepository(
        [
            KnowledgeEntry(
                id="faq-shipping",
                tenantId="stay",
                domainId="general",
                question="Do you have free shipping?",
                answer="Yes, shipping is free.",
                tags=["shipping"],
                active=True,
            )
        ]
    )
    governance_repo = StubGovernanceRepository(
        [
            GovernanceLog(
                id="log-1",
                tenantId="stay",
                clientId="whatsapp",
                userId="919845891194",
                decision=GovernanceDecision.ANSWERED,
                combinedText="Do you have free shipping?",
                answerSupplied="Yes, shipping is free.",
                metadata={
                    "sessionId": "session-1",
                    "workflow": "workflow_b",
                },
                timestamp=datetime(2026, 4, 25, 9, 6, tzinfo=timezone.utc),
            )
        ]
    )
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
            "supportEmail": "support@stayparfums.com",
            "domains": [{"domainId": "general", "name": "General"}],
            "settings": {"confidenceThreshold": 0.75},
            "brandVoice": {"tone": "Warm, polished, premium"},
            "onboarding": {"status": "completed"},
        },
        integrations=[
            {
                "tenantId": "stay",
                "provider": "whatsapp",
                "status": "connected",
                "health": "healthy",
                "accessToken": "super-secret-token",
            }
        ],
    )
    database = TestDatabase(
        tenant_repo=tenant_repo,
        session_repo=session_repo,
        knowledge_repo=knowledge_repo,
        governance_repo=governance_repo,
    )
    app = create_app(
        settings=_settings(DASHBOARD_AUTH_MODE="trusted_headers"),
        database=database,
    )

    with TestClient(app) as client:
        tenant_response = client.get("/api/tenant", headers=_trusted_headers())
        overview_response = client.get("/api/overview", headers=_trusted_headers())
        sessions_response = client.get("/api/sessions", headers=_trusted_headers())
        session_detail_response = client.get("/api/sessions/session-1", headers=_trusted_headers())
        kb_response = client.get("/api/knowledge-base", headers=_trusted_headers())
        test_question_response = client.post(
            "/api/test-question",
            json={"question": "Do you have free shipping?", "domainId": "general"},
            headers=_trusted_headers(),
        )
        brand_response = client.get("/api/brand-voice", headers=_trusted_headers())
        governance_response = client.get("/api/governance", headers=_trusted_headers())
        integrations_response = client.get("/api/integrations", headers=_trusted_headers())

    assert tenant_response.status_code == 200
    assert tenant_response.json()["tenantId"] == "stay"
    assert tenant_response.json()["supportEmail"] == "support@stayparfums.com"

    assert overview_response.status_code == 200
    assert overview_response.json()["metrics"]["aiResolved"] == 1
    assert overview_response.json()["metrics"]["deflectionRate"] == 1.0

    assert sessions_response.status_code == 200
    assert sessions_response.json()["sessions"][0]["tenantId"] == "stay"
    assert sessions_response.json()["sessions"][0]["latestMessage"] == "Do you have free shipping?"

    assert session_detail_response.status_code == 200
    assert session_detail_response.json()["session"]["id"] == "session-1"
    assert session_detail_response.json()["session"]["dashboardStatus"] == "resolved"
    assert session_detail_response.json()["governanceLogs"][0]["id"] == "log-1"

    assert kb_response.status_code == 200
    assert kb_response.json()["entries"][0]["id"] == "faq-shipping"

    assert test_question_response.status_code == 200
    assert test_question_response.json()["decision"] == "answered"
    assert test_question_response.json()["response"] == "Yes, shipping is free."
    assert test_question_response.json()["matchedKnowledgeBaseEntry"]["id"] == "faq-shipping"

    assert brand_response.status_code == 200
    assert brand_response.json()["brandVoice"]["tone"] == "Warm, polished, premium"

    assert governance_response.status_code == 200
    assert governance_response.json()["logs"][0]["decision"] == "answered"

    assert integrations_response.status_code == 200
    whatsapp = integrations_response.json()["integrations"][0]
    assert whatsapp["provider"] == "whatsapp"
    assert whatsapp["accessToken"] == "[redacted]"


def test_dashboard_write_endpoints_enforce_roles_and_write_audit_logs() -> None:
    """Owner/admin dashboard writes should mutate tenant data and create audit logs."""

    audit_repo = StubAuditRepository()
    knowledge_repo = StubKnowledgeRepository(
        [
            KnowledgeEntry(
                id="faq-shipping",
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
        settings=_settings(DASHBOARD_AUTH_MODE="trusted_headers"),
        database=database,
    )

    with TestClient(app) as client:
        tenant_response = client.patch(
            "/api/tenant",
            json={
                "tenantName": "Stay Parfums India",
                "settings": {"confidenceThreshold": 0.82, "ignoredSetting": True},
            },
            headers=_trusted_headers(),
        )
        brand_response = client.patch(
            "/api/brand-voice",
            json={"tone": "Warm, polished", "avoid": ["overpromising"]},
            headers=_trusted_headers(),
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
            headers=_trusted_headers(),
        )
        update_response = client.patch(
            "/api/knowledge-base/faq-shipping",
            json={"answer": "Yes, shipping is free on all orders."},
            headers=_trusted_headers(),
        )
        delete_response = client.delete(
            "/api/knowledge-base/faq-shipping",
            headers=_trusted_headers(),
        )
        integration_response = client.patch(
            "/api/integrations/whatsapp",
            json={"status": "connected", "health": "healthy"},
            headers=_trusted_headers(),
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

    assert [log["action"] for log in audit_repo.logs] == [
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
        settings=_settings(DASHBOARD_AUTH_MODE="trusted_headers"),
        database=database,
    )

    with TestClient(app) as client:
        role_response = client.patch(
            "/api/brand-voice",
            json={"tone": "Warm"},
            headers=_trusted_headers(),
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
        settings=_settings(DASHBOARD_AUTH_MODE="trusted_headers"),
        database=owner_database,
    )

    with TestClient(owner_app) as client:
        secret_response = client.patch(
            "/api/integrations/whatsapp",
            json={"metadata": {"accessToken": "do-not-store-here"}},
            headers=_trusted_headers(),
        )

    assert secret_response.status_code == 400
    assert secret_response.json()["detail"] == "integration secrets must not be submitted to this endpoint"


def test_billing_checkout_session_allows_inactive_owner(monkeypatch) -> None:
    """Owners should be able to recover billing even when subscription is inactive."""

    captured: dict[str, Any] = {}

    async def fake_stripe_post(path: str, *, secret_key: str, data: Mapping[str, Any]):
        captured["path"] = path
        captured["secret_key"] = secret_key
        captured["data"] = dict(data)
        return {"id": "cs_test_123", "url": "https://checkout.stripe.test/session"}

    monkeypatch.setattr("svmp_core.routes.billing._stripe_post", fake_stripe_post)

    database = TestDatabase(
        tenant_repo=StubTenantRepository(
            {
                "tenantId": "stay",
                "tenantName": "Stay Parfums",
                "role": "owner",
                "subscriptionStatus": "past_due",
            },
            tenant_document={"tenantId": "stay", "tenantName": "Stay Parfums"},
        ),
        billing_repo=StubBillingRepository(
            [{"tenantId": "stay", "stripeCustomerId": "cus_123", "status": "past_due"}]
        ),
    )
    app = create_app(
        settings=_settings(
            DASHBOARD_AUTH_MODE="trusted_headers",
            DASHBOARD_APP_URL="https://app.svmpsystems.com",
            STRIPE_SECRET_KEY="sk_test_123",
            STRIPE_PRICE_ID="price_123",
        ),
        database=database,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/billing/create-checkout-session",
            headers=_trusted_headers(),
        )

    assert response.status_code == 200
    assert response.json() == {
        "id": "cs_test_123",
        "url": "https://checkout.stripe.test/session",
    }
    assert captured["path"] == "/checkout/sessions"
    assert captured["secret_key"] == "sk_test_123"
    assert captured["data"]["customer"] == "cus_123"
    assert captured["data"]["metadata[tenantId]"] == "stay"


def test_billing_checkout_session_rejects_non_owner() -> None:
    """Billing session creation should be owner-only."""

    app = create_app(
        settings=_settings(
            DASHBOARD_AUTH_MODE="trusted_headers",
            STRIPE_SECRET_KEY="sk_test_123",
            STRIPE_PRICE_ID="price_123",
        ),
        database=TestDatabase(
            tenant_repo=StubTenantRepository(
                {
                    "tenantId": "stay",
                    "tenantName": "Stay Parfums",
                    "role": "admin",
                    "subscriptionStatus": "active",
                }
            )
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/billing/create-checkout-session",
            headers=_trusted_headers(user_id="admin_123"),
        )

    assert response.status_code == 403


def test_stripe_webhook_verifies_signature_and_processes_once() -> None:
    """Stripe webhooks should verify signatures and process events idempotently."""

    billing_repo = StubBillingRepository()
    provider_events_repo = StubProviderEventRepository()
    tenant_repo = StubTenantRepository(
        {
            "tenantId": "stay",
            "tenantName": "Stay Parfums",
            "role": "owner",
            "subscriptionStatus": "none",
        },
        tenant_document={"tenantId": "stay", "tenantName": "Stay Parfums"},
    )
    database = TestDatabase(
        tenant_repo=tenant_repo,
        billing_repo=billing_repo,
        provider_events_repo=provider_events_repo,
    )
    app = create_app(
        settings=_settings(
            STRIPE_WEBHOOK_SECRET="whsec_test",
        ),
        database=database,
    )
    event = {
        "id": "evt_123",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "stay",
                "customer": "cus_123",
                "subscription": "sub_123",
                "metadata": {"tenantId": "stay"},
            }
        },
    }
    raw_body = json.dumps(event, separators=(",", ":")).encode("utf-8")
    headers = {
        "Stripe-Signature": _stripe_signature(raw_body, "whsec_test"),
        "Content-Type": "application/json",
    }

    with TestClient(app) as client:
        first_response = client.post("/api/billing/webhook", content=raw_body, headers=headers)
        second_response = client.post("/api/billing/webhook", content=raw_body, headers=headers)

    assert first_response.status_code == 200
    assert first_response.json()["status"] == "processed"
    assert first_response.json()["tenantId"] == "stay"
    assert second_response.status_code == 200
    assert second_response.json()["status"] == "duplicate"

    stored_billing = billing_repo.records["stay"]
    assert stored_billing["status"] == "active"
    assert stored_billing["stripeCustomerId"] == "cus_123"
    assert stored_billing["stripeSubscriptionId"] == "sub_123"
    assert tenant_repo._tenant_document["billing"]["status"] == "active"


def test_stripe_webhook_rejects_invalid_signature() -> None:
    """Stripe webhooks should reject invalid signatures before processing."""

    app = create_app(
        settings=_settings(
            STRIPE_WEBHOOK_SECRET="whsec_test",
        ),
        database=TestDatabase(),
    )
    body = b'{"id":"evt_bad","type":"checkout.session.completed","data":{"object":{}}}'

    with TestClient(app) as client:
        response = client.post(
            "/api/billing/webhook",
            content=body,
            headers={
                "Stripe-Signature": "t=1700000000,v1=not-valid",
                "Content-Type": "application/json",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] in {
        "invalid Stripe signature",
        "Stripe signature timestamp is outside tolerance",
    }


def test_internal_job_routes_accept_vercel_cron_secret_and_support_get(monkeypatch) -> None:
    """Vercel cron should be able to call internal routes with GET and CRON_SECRET."""

    results = iter(
        [
            SimpleRunResult(processed=True, session_id="session-1", decision="answered"),
            SimpleRunResult(processed=True, session_id="session-2", decision="escalated"),
        ]
    )

    async def fake_run_workflow_b(database, *, settings=None):
        try:
            current = next(results)
        except StopIteration:
            return SimpleRunResult(processed=False, session_id=None, decision=None)
        return current

    monkeypatch.setattr("svmp_core.routes.internal_jobs.run_workflow_b", fake_run_workflow_b)

    app = create_app(
        settings=_settings(CRON_SECRET="cron-secret", WORKFLOW_B_MAX_BATCH_SIZE=2),
        database=TestDatabase(),
    )

    with TestClient(app) as client:
        response = client.get(
            "/internal/jobs/process-ready-sessions",
            params={"maxRuns": 100},
            headers={"Authorization": "Bearer cron-secret"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "processedCount": 2,
        "drained": False,
        "capacityReached": True,
        "maxRunsRequested": 100,
        "maxRunsApplied": 2,
        "runs": [
            {
                "sessionId": "session-1",
                "decision": "answered",
                "domainId": None,
                "matcherUsed": None,
                "reason": None,
            },
            {
                "sessionId": "session-2",
                "decision": "escalated",
                "domainId": None,
                "matcherUsed": None,
                "reason": None,
            },
        ],
    }


def test_internal_cleanup_route_accepts_post_and_header_secret(monkeypatch) -> None:
    """Internal cleanup should accept explicit header secrets for non-Vercel callers."""

    async def fake_run_workflow_c(database, *, settings=None):
        return SimpleCleanupResult(
            stale_sessions_found=3,
            governance_logs_written=3,
            sessions_deleted=3,
            cutoff_time=datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc),
        )

    monkeypatch.setattr("svmp_core.routes.internal_jobs.run_workflow_c", fake_run_workflow_c)

    app = create_app(
        settings=_settings(INTERNAL_JOB_SECRET="job-secret"),
        database=TestDatabase(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/internal/jobs/cleanup-stale-sessions",
            headers={"X-SVMP-Job-Secret": "job-secret"},
        )

    assert response.status_code == 200
    assert response.json()["staleSessionsFound"] == 3
    assert response.json()["governanceLogsWritten"] == 3
    assert response.json()["sessionsDeleted"] == 3


class SimpleRunResult:
    """Small helper matching the subset of Workflow B fields used by internal jobs."""

    def __init__(self, *, processed: bool, session_id: str | None, decision: str | None) -> None:
        self.processed = processed
        self.session_id = session_id
        self.decision = SimpleDecision(decision) if decision is not None else None
        self.domain_id = None
        self.matcher_used = None
        self.reason = None


class SimpleDecision:
    """Small enum-like wrapper used by SimpleRunResult."""

    def __init__(self, value: str) -> None:
        self.value = value


class SimpleCleanupResult:
    """Small helper matching the Workflow C response contract."""

    def __init__(
        self,
        *,
        stale_sessions_found: int,
        governance_logs_written: int,
        sessions_deleted: int,
        cutoff_time: datetime,
    ) -> None:
        self.stale_sessions_found = stale_sessions_found
        self.governance_logs_written = governance_logs_written
        self.sessions_deleted = sessions_deleted
        self.cutoff_time = cutoff_time
