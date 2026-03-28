"""Knowledge-base models."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class KnowledgeEntry(BaseModel):
    """Tenant-scoped FAQ entry."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str | None = Field(default=None, alias="_id")
    tenant_id: str = Field(alias="tenantId")
    domain_id: str = Field(alias="domainId")
    question: str
    answer: str
    tags: list[str] = Field(default_factory=list)
    active: bool = True
    created_at: datetime = Field(default_factory=_utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=_utcnow, alias="updatedAt")
