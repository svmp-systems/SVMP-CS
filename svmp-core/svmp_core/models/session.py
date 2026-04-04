"""Session-state models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def _ensure_utc(value: datetime) -> datetime:
    """Normalize datetimes to timezone-aware UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class MessageItem(BaseModel):
    """A single inbound user message fragment."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    text: str
    at: datetime = Field(default_factory=_utcnow)

    @field_validator("at")
    @classmethod
    def _normalize_at(cls, value: datetime) -> datetime:
        """Treat naive datetimes from Mongo as UTC."""

        return _ensure_utc(value)


class SessionState(BaseModel):
    """Active mutable session state used by workflows A/B/C."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str | None = Field(default=None, alias="_id")
    tenant_id: str = Field(alias="tenantId")
    client_id: str = Field(alias="clientId")
    user_id: str = Field(alias="userId")
    provider: str | None = None
    status: Literal["open", "closed"] = "open"
    processing: bool = False
    escalate: bool = False
    pending_escalation: bool = Field(default=False, alias="pendingEscalation")
    pending_escalation_expires_at: datetime | None = Field(default=None, alias="pendingEscalationExpiresAt")
    pending_escalation_metadata: dict[str, Any] = Field(default_factory=dict, alias="pendingEscalationMetadata")
    context: list[str] = Field(default_factory=list)
    messages: list[MessageItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=_utcnow, alias="updatedAt")
    debounce_expires_at: datetime = Field(default_factory=_utcnow, alias="debounceExpiresAt")

    @field_validator("created_at", "updated_at", "debounce_expires_at", "pending_escalation_expires_at")
    @classmethod
    def _normalize_session_times(cls, value: datetime | None) -> datetime | None:
        """Treat naive datetimes from Mongo as UTC."""

        if value is None:
            return None
        return _ensure_utc(value)
