"""Normalized webhook payload models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WebhookPayload(BaseModel):
    """Normalized inbound payload used by the code version."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    tenant_id: str = Field(alias="tenantId")
    client_id: str = Field(alias="clientId")
    user_id: str = Field(alias="userId")
    text: str
