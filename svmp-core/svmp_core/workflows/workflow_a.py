"""Workflow A: ingest inbound message fragments into session state."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import ValidationError as PydanticValidationError

from svmp_core.config import Settings, get_settings
from svmp_core.core import IdentityFrame
from svmp_core.db.base import Database
from svmp_core.exceptions import DatabaseError, ValidationError
from svmp_core.models import MessageItem, SessionState, WebhookPayload


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
    normalized_text = payload.text.strip()

    if not normalized_text:
        raise ValidationError("inbound text must not be blank")

    try:
        identity = IdentityFrame.from_webhook_payload(payload)
    except PydanticValidationError as exc:
        raise ValidationError("invalid inbound identity") from exc

    debounce_expires_at = current_time + timedelta(milliseconds=runtime_settings.DEBOUNCE_MS)
    new_message = MessageItem(text=normalized_text, at=current_time)

    existing_session = await database.session_state.get_by_identity(*identity.as_tuple())

    if existing_session is None:
        session = SessionState(
            tenant_id=identity.tenant_id,
            client_id=identity.client_id,
            user_id=identity.user_id,
            provider=payload.provider,
            processing=False,
            context=[],
            messages=[new_message],
            created_at=current_time,
            updated_at=current_time,
            debounce_expires_at=debounce_expires_at,
        )
        return await database.session_state.create(session)

    if existing_session.id is None:
        raise DatabaseError("existing session missing id")

    updated_session = await database.session_state.update_by_id(
        existing_session.id,
        {
            "messages": [*existing_session.messages, new_message],
            "provider": payload.provider,
            "status": "open",
            "updated_at": current_time,
            "debounce_expires_at": debounce_expires_at,
            "processing": False,
        },
    )

    if updated_session is None:
        raise DatabaseError("failed to update existing session")

    return updated_session
