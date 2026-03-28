"""Application settings and config helpers for SVMP."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed environment-backed settings for the SVMP core."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "SVMP"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    PORT: int = 8000

    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "svmp"
    MONGODB_SESSION_COLLECTION: str = "session_state"
    MONGODB_KB_COLLECTION: str = "knowledge_base"
    MONGODB_GOVERNANCE_COLLECTION: str = "governance_logs"
    MONGODB_TENANTS_COLLECTION: str = "tenants"

    OPENAI_API_KEY: SecretStr | None = None
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    LLM_MODEL: str = "gpt-4o-mini"

    WHATSAPP_TOKEN: SecretStr | None = None
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_VERIFY_TOKEN: SecretStr | None = None

    DEBOUNCE_MS: int = 2500
    SIMILARITY_THRESHOLD: float = 0.75
    WORKFLOW_B_INTERVAL_SECONDS: int = 1
    WORKFLOW_C_INTERVAL_HOURS: int = 24


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings object for application use."""

    return Settings()


def get_tenant_confidence_threshold(
    tenant_document: Mapping[str, Any] | None,
) -> float:
    """Resolve a tenant confidence threshold or fail hard if it is missing.

    The codebase keeps a global fallback threshold in settings for system defaults
    and local development, but tenant-driven runtime logic should fail fast when
    tenant configuration is missing or malformed so the caller can escalate safely.
    """

    if tenant_document is None:
        raise ValueError("tenant document missing")

    tenant_settings = tenant_document.get("settings")
    if not isinstance(tenant_settings, Mapping):
        raise ValueError("tenant settings missing")

    threshold = tenant_settings.get("confidenceThreshold")
    if threshold is None:
        raise ValueError("tenant confidenceThreshold missing")

    return float(threshold)


settings = get_settings()
