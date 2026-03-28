"""Governance-log models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class GovernanceDecision(StrEnum):
    """Supported governance outcomes."""

    ANSWERED = "answered"
    ESCALATED = "escalated"
    CLOSED = "closed"


class GovernanceLog(BaseModel):
    """Immutable audit record for an automated decision."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str | None = Field(default=None, alias="_id")
    tenant_id: str = Field(alias="tenantId")
    client_id: str = Field(alias="clientId")
    user_id: str = Field(alias="userId")
    decision: GovernanceDecision
    similarity_score: float | None = Field(default=None, alias="similarityScore")
    combined_text: str = Field(alias="combinedText")
    answer_supplied: str | None = Field(default=None, alias="answerSupplied")
    timestamp: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
