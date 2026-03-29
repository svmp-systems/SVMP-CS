"""Canonical identity tuple helpers for conversation-scoped workflows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from svmp_core.models.webhook import WebhookPayload


class IdentityFrame(BaseModel):
    """Validated identity tuple used to address a single conversation."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    tenant_id: str = Field(alias="tenantId")
    client_id: str = Field(alias="clientId")
    user_id: str = Field(alias="userId")

    @field_validator("tenant_id", "client_id", "user_id")
    @classmethod
    def _normalize_required_identity_part(cls, value: str) -> str:
        """Trim identity fields and reject blank values."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("identity fields must not be blank")
        return normalized

    def as_tuple(self) -> tuple[str, str, str]:
        """Return the canonical identity tuple used by repositories."""

        return (self.tenant_id, self.client_id, self.user_id)

    @classmethod
    def from_webhook_payload(cls, payload: WebhookPayload) -> "IdentityFrame":
        """Build an identity frame from a normalized webhook payload."""

        return cls(
            tenant_id=payload.tenant_id,
            client_id=payload.client_id,
            user_id=payload.user_id,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "IdentityFrame":
        """Build an identity frame from a generic mapping."""

        return cls(**dict(value))
