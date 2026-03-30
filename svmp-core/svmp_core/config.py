"""Application settings and config helpers for SVMP."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from svmp_core.exceptions import ConfigError


def _normalized_secret(value: SecretStr | None) -> str | None:
    """Return a stripped secret value when present."""

    if value is None:
        return None

    normalized = value.get_secret_value().strip()
    if not normalized:
        return None

    return normalized


def _missing_string(value: str | None) -> bool:
    """Return whether a string setting is missing or blank."""

    return value is None or not value.strip()


class Settings(BaseSettings):
    """Typed environment-backed settings for the SVMP core."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "SVMP"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    PORT: int = 8000

    MONGODB_URI: str | None = None
    MONGODB_DB_NAME: str = "svmp"
    MONGODB_SESSION_COLLECTION: str = "session_state"
    MONGODB_KB_COLLECTION: str = "knowledge_base"
    MONGODB_GOVERNANCE_COLLECTION: str = "governance_logs"
    MONGODB_TENANTS_COLLECTION: str = "tenants"

    OPENAI_API_KEY: SecretStr | None = None
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    LLM_MODEL: str = "gpt-4o-mini"
    USE_OPENAI_MATCHER: bool = False
    OPENAI_SHADOW_MODE: bool = False
    OPENAI_MATCHER_CANDIDATE_LIMIT: int = 8

    WHATSAPP_PROVIDER: str = "meta"
    WHATSAPP_TOKEN: SecretStr | None = None
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_VERIFY_TOKEN: SecretStr | None = None

    DEBOUNCE_MS: int = 2500
    SIMILARITY_THRESHOLD: float = 0.75
    WORKFLOW_B_INTERVAL_SECONDS: int = 1
    WORKFLOW_C_INTERVAL_HOURS: int = 24

    def validate_runtime(self) -> None:
        """Fail fast when the live demo runtime is missing required env values."""

        missing: list[str] = []

        if _missing_string(self.MONGODB_URI):
            missing.append("MONGODB_URI")
        if self.OPENAI_API_KEY is None or _normalized_secret(self.OPENAI_API_KEY) is None:
            missing.append("OPENAI_API_KEY")
        provider = self.WHATSAPP_PROVIDER.strip().lower()
        if provider == "meta":
            if self.WHATSAPP_TOKEN is None or _normalized_secret(self.WHATSAPP_TOKEN) is None:
                missing.append("WHATSAPP_TOKEN")
            if _missing_string(self.WHATSAPP_PHONE_NUMBER_ID):
                missing.append("WHATSAPP_PHONE_NUMBER_ID")
            if self.WHATSAPP_VERIFY_TOKEN is None or _normalized_secret(self.WHATSAPP_VERIFY_TOKEN) is None:
                missing.append("WHATSAPP_VERIFY_TOKEN")
        elif provider != "normalized":
            missing.append("WHATSAPP_PROVIDER")

        if missing:
            raise ConfigError(
                "missing required runtime configuration: "
                + ", ".join(sorted(missing))
            )


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
