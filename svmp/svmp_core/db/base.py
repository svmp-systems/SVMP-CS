"""Abstract persistence contracts for SVMP."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from svmp_core.models.governance import GovernanceLog
from svmp_core.models.knowledge import KnowledgeEntry
from svmp_core.models.session import SessionState


class SessionStateRepository(ABC):
    """Persistence contract for active session state."""

    @abstractmethod
    async def get_by_identity(
        self,
        tenant_id: str,
        client_id: str,
        user_id: str,
    ) -> SessionState | None:
        """Return the active session for an identity tuple if it exists."""

    @abstractmethod
    async def create(self, session: SessionState) -> SessionState:
        """Create and return a new session-state document."""

    @abstractmethod
    async def update_by_id(
        self,
        session_id: str,
        data: Mapping[str, Any],
    ) -> SessionState | None:
        """Apply a partial update and return the updated session if found."""

    @abstractmethod
    async def acquire_ready_session(self, now: datetime) -> SessionState | None:
        """Atomically acquire one ready session for Workflow B processing."""

    @abstractmethod
    async def delete_stale_sessions(self, before: datetime) -> int:
        """Delete stale sessions and return the number removed."""

    async def list_by_tenant(
        self,
        tenant_id: str,
        *,
        limit: int = 50,
    ) -> list[SessionState]:
        """List recent active sessions for a tenant when supported."""

        return []


class KnowledgeBaseRepository(ABC):
    """Persistence contract for tenant-scoped FAQ entries."""

    @abstractmethod
    async def list_active_by_tenant_and_domain(
        self,
        tenant_id: str,
        domain_id: str,
    ) -> list[KnowledgeEntry]:
        """List active FAQ entries for a tenant/domain pair."""

    async def list_by_tenant(
        self,
        tenant_id: str,
        *,
        active: bool | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[KnowledgeEntry]:
        """List tenant FAQ entries for dashboard reads when supported."""

        return []

    async def create(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        """Create and return a tenant-scoped FAQ entry when supported."""

        raise NotImplementedError

    async def update_by_id(
        self,
        tenant_id: str,
        entry_id: str,
        data: Mapping[str, Any],
    ) -> KnowledgeEntry | None:
        """Update a tenant-scoped FAQ entry when supported."""

        return None

    async def deactivate_by_id(
        self,
        tenant_id: str,
        entry_id: str,
        data: Mapping[str, Any],
    ) -> KnowledgeEntry | None:
        """Soft-delete a tenant-scoped FAQ entry when supported."""

        return await self.update_by_id(tenant_id, entry_id, data)


class GovernanceLogRepository(ABC):
    """Persistence contract for immutable governance logs."""

    @abstractmethod
    async def create(self, log: GovernanceLog) -> GovernanceLog:
        """Insert and return a governance log record."""

    async def list_by_tenant(
        self,
        tenant_id: str,
        *,
        limit: int = 100,
    ) -> list[GovernanceLog]:
        """List recent governance logs for a tenant when supported."""

        return []

    async def count_by_decision(self, tenant_id: str) -> Mapping[str, int]:
        """Return tenant governance counts grouped by decision when supported."""

        return {}


class TenantRepository(ABC):
    """Persistence contract for tenant metadata and routing config."""

    @abstractmethod
    async def get_by_tenant_id(self, tenant_id: str) -> Mapping[str, Any] | None:
        """Return the tenant configuration document if it exists."""

    async def update_by_tenant_id(
        self,
        tenant_id: str,
        data: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        """Update tenant metadata when supported."""

        return None

    async def resolve_tenant_id_for_provider(
        self,
        *,
        provider: str,
        identities: Sequence[str],
    ) -> str | None:
        """Resolve a tenant id from provider channel identities when supported."""

        return None

    async def resolve_dashboard_tenant_context(
        self,
        *,
        clerk_organization_id: str,
        clerk_user_id: str,
    ) -> Mapping[str, Any] | None:
        """Resolve tenant membership, role, and billing state for dashboard APIs."""

        return None

    async def list_integration_status(
        self,
        tenant_id: str,
    ) -> list[Mapping[str, Any]]:
        """List tenant integration status records when supported."""

        return []

    async def update_integration_status(
        self,
        tenant_id: str,
        provider: str,
        data: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        """Update one tenant integration status record when supported."""

        return None


class AuditLogRepository(ABC):
    """Persistence contract for dashboard administrative audit logs."""

    async def create(self, log: Mapping[str, Any]) -> Mapping[str, Any]:
        """Insert an audit log record when supported."""

        return dict(log)


class BillingSubscriptionRepository(ABC):
    """Persistence contract for Stripe subscription state."""

    async def get_by_tenant_id(self, tenant_id: str) -> Mapping[str, Any] | None:
        """Return subscription state by tenant when supported."""

        return None

    async def upsert_by_tenant_id(
        self,
        tenant_id: str,
        data: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        """Upsert subscription state by tenant when supported."""

        return None

    async def get_by_stripe_ids(
        self,
        *,
        stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        """Find subscription state from Stripe ids when supported."""

        return None


class ProviderEventRepository(ABC):
    """Persistence contract for idempotent provider webhook events."""

    async def record_once(
        self,
        *,
        provider: str,
        event_id: str,
        event_type: str,
        tenant_id: str | None,
        payload_hash: str,
    ) -> bool:
        """Record a provider event, returning False for duplicates."""

        return True


class Database(ABC):
    """Top-level database contract for repository access and lifecycle."""

    @property
    @abstractmethod
    def session_state(self) -> SessionStateRepository:
        """Return the session-state repository."""

    @property
    @abstractmethod
    def knowledge_base(self) -> KnowledgeBaseRepository:
        """Return the knowledge-base repository."""

    @property
    @abstractmethod
    def governance_logs(self) -> GovernanceLogRepository:
        """Return the governance-log repository."""

    @property
    @abstractmethod
    def tenants(self) -> TenantRepository:
        """Return the tenant repository."""

    @property
    def audit_logs(self) -> AuditLogRepository:
        """Return the dashboard audit-log repository."""

        return AuditLogRepository()

    @property
    def billing_subscriptions(self) -> BillingSubscriptionRepository:
        """Return the billing subscription repository."""

        return BillingSubscriptionRepository()

    @property
    def provider_events(self) -> ProviderEventRepository:
        """Return the provider-event idempotency repository."""

        return ProviderEventRepository()

    @abstractmethod
    async def connect(self) -> None:
        """Initialize database resources."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Release database resources."""
