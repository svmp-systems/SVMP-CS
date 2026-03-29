"""Integration-style tests for Workflow C session cleanup."""

from __future__ import annotations

from datetime import datetime, timezone

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
from svmp_core.models import GovernanceDecision, GovernanceLog, KnowledgeEntry, SessionState
from svmp_core.workflows import run_workflow_c


class CleanupSessionRepository(SessionStateRepository):
    """In-memory session repository with explicit stale-session support."""

    def __init__(self, stale_sessions: list[SessionState]) -> None:
        self._stale_sessions = [session.model_copy(deep=True) for session in stale_sessions]
        self.cutoff_seen = None

    async def get_by_identity(self, tenant_id: str, client_id: str, user_id: str):
        raise NotImplementedError

    async def create(self, session: SessionState):
        raise NotImplementedError

    async def update_by_id(self, session_id: str, data):
        raise NotImplementedError

    async def acquire_ready_session(self, now: datetime):
        raise NotImplementedError

    async def delete_stale_sessions(self, before: datetime) -> int:
        self.cutoff_seen = before
        deleted = len(self._stale_sessions)
        self._stale_sessions = []
        return deleted

    async def list_stale_sessions(self, before: datetime) -> list[SessionState]:
        self.cutoff_seen = before
        return [session.model_copy(deep=True) for session in self._stale_sessions]


class FailingCleanupSessionRepository(CleanupSessionRepository):
    """Repository variant that fails during deletion."""

    async def delete_stale_sessions(self, before: datetime) -> int:
        raise RuntimeError("mongo down")


class StubKnowledgeRepository(KnowledgeBaseRepository):
    async def list_active_by_tenant_and_domain(
        self,
        tenant_id: str,
        domain_id: str,
    ) -> list[KnowledgeEntry]:
        return []


class CapturingGovernanceRepository(GovernanceLogRepository):
    """Collect written governance logs for assertions."""

    def __init__(self) -> None:
        self.logs: list[GovernanceLog] = []

    async def create(self, log: GovernanceLog) -> GovernanceLog:
        stored = log.model_copy(deep=True)
        self.logs.append(stored)
        return stored


class StubTenantRepository(TenantRepository):
    async def get_by_tenant_id(self, tenant_id: str):
        return None


class CleanupDatabase(Database):
    """Database wrapper for Workflow C tests."""

    def __init__(self, session_repo: SessionStateRepository) -> None:
        self._session_state = session_repo
        self._knowledge_base = StubKnowledgeRepository()
        self._governance_logs = CapturingGovernanceRepository()
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
    """Return deterministic cleanup settings for tests."""

    return Settings(_env_file=None, WORKFLOW_C_INTERVAL_HOURS=24)


def _stale_session() -> SessionState:
    """Create a representative stale session document."""

    return SessionState(
        _id="session-stale-1",
        tenantId="Niyomilan",
        clientId="whatsapp",
        userId="9845891194",
        createdAt=datetime(2026, 3, 27, 9, 0, tzinfo=timezone.utc),
        updatedAt=datetime(2026, 3, 27, 9, 0, tzinfo=timezone.utc),
        debounceExpiresAt=datetime(2026, 3, 27, 9, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_workflow_c_cleans_up_stale_sessions_and_logs_closure() -> None:
    """Workflow C should log and delete stale sessions inside the retention window."""

    now = datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc)
    session_repo = CleanupSessionRepository([_stale_session()])
    database = CleanupDatabase(session_repo)

    result = await run_workflow_c(database, settings=_settings(), now=now)

    assert result.stale_sessions_found == 1
    assert result.governance_logs_written == 1
    assert result.sessions_deleted == 1
    assert result.cutoff_time == datetime(2026, 3, 29, 10, 0, tzinfo=timezone.utc)

    written_logs = database.governance_logs.logs
    assert len(written_logs) == 1
    assert written_logs[0].decision == GovernanceDecision.CLOSED
    assert written_logs[0].metadata == {"retentionHours": 24}


@pytest.mark.asyncio
async def test_workflow_c_reports_clean_no_op_when_no_stale_sessions_exist() -> None:
    """No-op cleanup runs should report zeros cleanly without writing logs."""

    now = datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc)
    session_repo = CleanupSessionRepository([])
    database = CleanupDatabase(session_repo)

    result = await run_workflow_c(database, settings=_settings(), now=now)

    assert result.stale_sessions_found == 0
    assert result.governance_logs_written == 0
    assert result.sessions_deleted == 0
    assert database.governance_logs.logs == []


@pytest.mark.asyncio
async def test_workflow_c_wraps_database_failures() -> None:
    """Database failures should be wrapped predictably for the scheduler/runtime."""

    database = CleanupDatabase(FailingCleanupSessionRepository([_stale_session()]))

    with pytest.raises(DatabaseError, match="workflow c cleanup failed"):
        await run_workflow_c(database, settings=_settings())
