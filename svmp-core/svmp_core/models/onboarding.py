"""Tenant onboarding models for website-driven KB generation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class TenantOnboardingRequest(BaseModel):
    """Inbound onboarding request submitted from a website form."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    tenant_id: str = Field(alias="tenantId")
    website_url: HttpUrl = Field(alias="websiteUrl")
    brand_voice: str | dict[str, Any] = Field(alias="brandVoice")
    tenant_name: str | None = Field(default=None, alias="tenantName")
    tags: list[str] = Field(default_factory=list)
    public_question_urls: list[HttpUrl] = Field(default_factory=list, alias="publicQuestionUrls")
    target_faq_count: int = Field(default=30, alias="targetFaqCount", ge=10, le=80)

    @field_validator("tenant_id")
    @classmethod
    def _normalize_tenant_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("tenantId must not be blank")
        return normalized

    @field_validator("tenant_name")
    @classmethod
    def _normalize_tenant_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class TenantOnboardingAccepted(BaseModel):
    """Immediate response returned when onboarding has been queued."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    status: str = "accepted"
    tenant_id: str = Field(alias="tenantId")
    onboarding_status: str = Field(alias="onboardingStatus")
    website_url: str = Field(alias="websiteUrl")


class TenantOnboardingStatusResponse(BaseModel):
    """Read model for tenant onboarding status checks."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    tenant_id: str = Field(alias="tenantId")
    website_url: str | None = Field(default=None, alias="websiteUrl")
    brand_voice: str | dict[str, Any] | None = Field(default=None, alias="brandVoice")
    onboarding: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = Field(default_factory=_utcnow, alias="updatedAt")
