"""Workflow A: ingest inbound message fragments into session state."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import ValidationError as PydanticValidationError

from svmp_core.config import Settings, get_settings
from svmp_core.core import IdentityFrame
from svmp_core.core.timing import LatencyTrace
from svmp_core.db.base import Database
from svmp_core.exceptions import DatabaseError, ValidationError
from svmp_core.logger import get_logger
from svmp_core.models import MessageItem, SessionState, WebhookPayload

logger = get_logger("svmp.workflows.workflow_a")


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


async def run_workflow_a(
    database: Database,
    payload: WebhookPayload,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> SessionState:
    """Create or update session state for a newly received inbound message."""

    runtime_settings = settings or get_settings()
    current_time = now or _utcnow()
    trace = LatencyTrace("workflow_a", started_at=current_time)
    normalized_text = payload.text.strip()

    if not normalized_text:
        raise ValidationError("inbound text must not be blank")

    try:
        with trace.step("workflow_a.identity.from_webhook_payload"):
            identity = IdentityFrame.from_webhook_payload(payload)
    except PydanticValidationError as exc:
        logger.exception(
            "workflow_a_failed",
            provider=payload.provider,
            tenantId=payload.tenant_id,
            clientId=payload.client_id,
            userId=payload.user_id,
            trace=trace.snapshot(outcome="failed", failureStage="identity_from_webhook_payload"),
        )
        raise ValidationError("invalid inbound identity") from exc

    debounce_expires_at = current_time + timedelta(milliseconds=runtime_settings.DEBOUNCE_MS)
    new_message = MessageItem(text=normalized_text, at=current_time)

    try:
        with trace.step("workflow_a.session_state.get_by_identity"):
            existing_session = await database.session_state.get_by_identity(*identity.as_tuple())

        if existing_session is None:
            session = SessionState(
                tenant_id=identity.tenant_id,
                client_id=identity.client_id,
                user_id=identity.user_id,
                provider=payload.provider,
                processing=False,
                escalate=False,
                context=[],
                messages=[new_message],
                created_at=current_time,
                updated_at=current_time,
                debounce_expires_at=debounce_expires_at,
            )
            with trace.step("workflow_a.session_state.create"):
                created_session = await database.session_state.create(session)
            logger.info(
                "workflow_a_completed",
                sessionId=created_session.id,
                provider=payload.provider,
                tenantId=identity.tenant_id,
                clientId=identity.client_id,
                userId=identity.user_id,
                debounceExpiresAt=debounce_expires_at.isoformat(),
                trace=trace.snapshot(outcome="created"),
            )
            return created_session

        if existing_session.id is None:
            raise DatabaseError("existing session missing id")

        with trace.step("workflow_a.session_state.update_by_id"):
            updated_session = await database.session_state.update_by_id(
                existing_session.id,
                {
                    "messages": [*existing_session.messages, new_message],
                    "provider": payload.provider,
                    "status": "open",
                    "updated_at": current_time,
                    "debounce_expires_at": debounce_expires_at,
                    "processing": False,
                    "pending_escalation": False,
                    "pending_escalation_expires_at": None,
                    "pending_escalation_metadata": {},
                },
            )

        if updated_session is None:
            raise DatabaseError("failed to update existing session")

        logger.info(
            "workflow_a_completed",
            sessionId=updated_session.id,
            provider=payload.provider,
            tenantId=identity.tenant_id,
            clientId=identity.client_id,
            userId=identity.user_id,
            debounceExpiresAt=debounce_expires_at.isoformat(),
            trace=trace.snapshot(
                outcome="updated",
                existingMessageCount=len(existing_session.messages),
                newMessageCount=len(updated_session.messages),
            ),
        )
        return updated_session
    except Exception:
        logger.exception(
            "workflow_a_failed",
            provider=payload.provider,
            tenantId=identity.tenant_id,
            clientId=identity.client_id,
            userId=identity.user_id,
            trace=trace.snapshot(outcome="failed"),
        )
        raise
