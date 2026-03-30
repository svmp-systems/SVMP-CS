"""Normalized webhook payload models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WebhookPayload(BaseModel):
    """Normalized inbound payload used by the code version."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    tenant_id: str = Field(alias="tenantId")
    client_id: str = Field(alias="clientId")
    user_id: str = Field(alias="userId")
    text: str
    provider: str = "normalized"
    external_message_id: str | None = Field(default=None, alias="externalMessageId")


class OutboundTextMessage(BaseModel):
    """Normalized outbound text message used by provider send interfaces."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    tenant_id: str = Field(alias="tenantId")
    client_id: str = Field(alias="clientId")
    user_id: str = Field(alias="userId")
    text: str
    provider: str = "normalized"


class OutboundSendResult(BaseModel):
    """Normalized provider send result surface."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    provider: str
    accepted: bool
    status: str
    external_message_id: str | None = Field(default=None, alias="externalMessageId")
    metadata: dict[str, Any] = Field(default_factory=dict)
