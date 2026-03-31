"""Session-state models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class MessageItem(BaseModel):
    """A single inbound user message fragment."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    text: str
    at: datetime = Field(default_factory=_utcnow)


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
    messages: list[MessageItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=_utcnow, alias="updatedAt")
    debounce_expires_at: datetime = Field(default_factory=_utcnow, alias="debounceExpiresAt")
