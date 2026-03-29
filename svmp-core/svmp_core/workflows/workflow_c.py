"""Workflow C: clean up stale session state and record closure logs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from svmp_core.config import Settings, get_settings
from svmp_core.core import IdentityFrame, build_closed_log
from svmp_core.db.base import Database
from svmp_core.exceptions import DatabaseError
from svmp_core.models import SessionState


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class WorkflowCResult:
    """Summary of a Workflow C cleanup run."""

    stale_sessions_found: int
    governance_logs_written: int
    sessions_deleted: int
    cutoff_time: datetime


async def run_workflow_c(
    database: Database,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> WorkflowCResult:
    """Delete stale sessions and record closure logs when session detail is available."""

    runtime_settings = settings or get_settings()
    current_time = now or _utcnow()
    cutoff_time = current_time - timedelta(hours=runtime_settings.WORKFLOW_C_INTERVAL_HOURS)

    list_stale = getattr(database.session_state, "list_stale_sessions", None)
    has_stale_listing = callable(list_stale)
    stale_sessions: list[SessionState] = []

    try:
        if has_stale_listing:
            stale_sessions = list(await list_stale(cutoff_time))

        logs_written = 0
        for session in stale_sessions:
            log = build_closed_log(
                IdentityFrame(
                    tenant_id=session.tenant_id,
                    client_id=session.client_id,
                    user_id=session.user_id,
                ),
                "stale session closed",
                metadata={"retentionHours": runtime_settings.WORKFLOW_C_INTERVAL_HOURS},
                timestamp=current_time,
            )
            await database.governance_logs.create(log)
            logs_written += 1

        deleted_count = await database.session_state.delete_stale_sessions(cutoff_time)
    except Exception as exc:  # pragma: no cover - defensive wrapper
        raise DatabaseError("workflow c cleanup failed") from exc

    stale_sessions_found = len(stale_sessions) if has_stale_listing else deleted_count

    return WorkflowCResult(
        stale_sessions_found=stale_sessions_found,
        governance_logs_written=logs_written,
        sessions_deleted=deleted_count,
        cutoff_time=cutoff_time,
    )
