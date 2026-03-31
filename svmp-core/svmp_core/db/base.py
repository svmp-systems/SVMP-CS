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


class KnowledgeBaseRepository(ABC):
    """Persistence contract for tenant-scoped FAQ entries."""

    @abstractmethod
    async def list_active_by_tenant_and_domain(
        self,
        tenant_id: str,
        domain_id: str,
    ) -> list[KnowledgeEntry]:
        """List active FAQ entries for a tenant/domain pair."""


class GovernanceLogRepository(ABC):
    """Persistence contract for immutable governance logs."""

    @abstractmethod
    async def create(self, log: GovernanceLog) -> GovernanceLog:
        """Insert and return a governance log record."""


class TenantRepository(ABC):
    """Persistence contract for tenant metadata and routing config."""

    @abstractmethod
    async def get_by_tenant_id(self, tenant_id: str) -> Mapping[str, Any] | None:
        """Return the tenant configuration document if it exists."""

    async def resolve_tenant_id_for_provider(
        self,
        *,
        provider: str,
        identities: Sequence[str],
    ) -> str | None:
        """Resolve a tenant id from provider channel identities when supported."""

        return None


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

    @abstractmethod
    async def connect(self) -> None:
        """Initialize database resources."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Release database resources."""
