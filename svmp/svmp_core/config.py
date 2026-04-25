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

    DATABASE_URL: str | None = None
    SHARED_KB_TENANT_ID: str = "__shared__"
    DB_AUTO_APPLY_MIGRATIONS: bool = False

    OPENAI_API_KEY: SecretStr | None = None
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    LLM_MODEL: str = "gpt-4.1"
    USE_OPENAI_MATCHER: bool = False
    OPENAI_SHADOW_MODE: bool = False
    OPENAI_MATCHER_CANDIDATE_LIMIT: int = 8

    WHATSAPP_PROVIDER: str = "meta"
    WHATSAPP_TOKEN: SecretStr | None = None
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_VERIFY_TOKEN: SecretStr | None = None
    META_APP_SECRET: SecretStr | None = None
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: SecretStr | None = None
    TWILIO_WHATSAPP_NUMBER: str | None = None
    WEBHOOK_PUBLIC_BASE_URL: str | None = None
    NORMALIZED_WEBHOOK_SECRET: SecretStr | None = None
    ALLOW_NORMALIZED_WEBHOOKS: bool = False

    DEBOUNCE_MS: int = 2500
    SIMILARITY_THRESHOLD: float = 0.75
    WORKFLOW_B_INTERVAL_SECONDS: int = 1
    WORKFLOW_B_PROCESSING_LOCK_TIMEOUT_SECONDS: int = 300
    WORKFLOW_B_MAX_BATCH_SIZE: int = 25
    WORKFLOW_C_INTERVAL_HOURS: int = 24
    ONBOARDING_FETCH_TIMEOUT_SECONDS: int = 10
    ONBOARDING_MAX_SITE_PAGES: int = 8
    ONBOARDING_MAX_PUBLIC_QA_URLS: int = 5
    ONBOARDING_MAX_SOURCE_CHARS_PER_PAGE: int = 5000
    ONBOARDING_FAQ_TARGET_COUNT: int = 30

    DASHBOARD_AUTH_MODE: str = "disabled"
    SUPABASE_PROJECT_URL: str | None = None
    SUPABASE_JWT_ISSUER: str | None = None
    SUPABASE_JWKS_URL: str | None = None
    SUPABASE_JWT_AUDIENCE: str | None = "authenticated"
    DASHBOARD_APP_URL: str | None = None
    DASHBOARD_CORS_ORIGINS: str | None = None

    INTERNAL_JOB_SECRET: SecretStr | None = None
    CRON_SECRET: SecretStr | None = None

    STRIPE_SECRET_KEY: SecretStr | None = None
    STRIPE_WEBHOOK_SECRET: SecretStr | None = None
    STRIPE_PRICE_ID: str | None = None
    BILLING_MODE: str = "manual"

    def supabase_auth_issuer(self) -> str | None:
        """Return the normalized Supabase Auth issuer when configured."""

        if not _missing_string(self.SUPABASE_JWT_ISSUER):
            return self.SUPABASE_JWT_ISSUER.strip().rstrip("/")
        if not _missing_string(self.SUPABASE_PROJECT_URL):
            return f"{self.SUPABASE_PROJECT_URL.strip().rstrip('/')}/auth/v1"
        return None

    def supabase_jwks_url(self) -> str | None:
        """Return the normalized Supabase JWKS URL when configured."""

        if not _missing_string(self.SUPABASE_JWKS_URL):
            return self.SUPABASE_JWKS_URL.strip()

        issuer = self.supabase_auth_issuer()
        if issuer is None:
            return None
        return f"{issuer}/.well-known/jwks.json"

    def internal_job_secret(self) -> str | None:
        """Return the shared secret accepted by internal job endpoints."""

        return _normalized_secret(self.INTERNAL_JOB_SECRET) or _normalized_secret(self.CRON_SECRET)

    def validate_runtime(self) -> None:
        """Fail fast when the live runtime is missing required env values."""

        missing: list[str] = []
        production = self.APP_ENV.strip().lower() in {"prod", "production"}

        if _missing_string(self.DATABASE_URL):
            missing.append("DATABASE_URL")
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
            if self.META_APP_SECRET is None or _normalized_secret(self.META_APP_SECRET) is None:
                missing.append("META_APP_SECRET")
        elif provider == "twilio":
            if _missing_string(self.TWILIO_ACCOUNT_SID):
                missing.append("TWILIO_ACCOUNT_SID")
            if self.TWILIO_AUTH_TOKEN is None or _normalized_secret(self.TWILIO_AUTH_TOKEN) is None:
                missing.append("TWILIO_AUTH_TOKEN")
            if _missing_string(self.TWILIO_WHATSAPP_NUMBER):
                missing.append("TWILIO_WHATSAPP_NUMBER")
        elif provider == "normalized":
            if (
                not self.ALLOW_NORMALIZED_WEBHOOKS
                and (
                    self.NORMALIZED_WEBHOOK_SECRET is None
                    or _normalized_secret(self.NORMALIZED_WEBHOOK_SECRET) is None
                )
            ):
                missing.append("NORMALIZED_WEBHOOK_SECRET")
        else:
            missing.append("WHATSAPP_PROVIDER")

        dashboard_auth_mode = self.DASHBOARD_AUTH_MODE.strip().lower()
        if production and dashboard_auth_mode != "supabase":
            missing.append("DASHBOARD_AUTH_MODE=supabase")
        if dashboard_auth_mode == "supabase" or production:
            if _missing_string(self.SUPABASE_PROJECT_URL):
                missing.append("SUPABASE_PROJECT_URL")
            if self.supabase_auth_issuer() is None:
                missing.append("SUPABASE_JWT_ISSUER")
            if self.supabase_jwks_url() is None:
                missing.append("SUPABASE_JWKS_URL")
            if production and _missing_string(self.DASHBOARD_APP_URL):
                missing.append("DASHBOARD_APP_URL")

        if production and self.internal_job_secret() is None:
            missing.append("INTERNAL_JOB_SECRET or CRON_SECRET")

        billing_mode = self.BILLING_MODE.strip().lower()
        if billing_mode not in {"manual", "stripe"}:
            missing.append("BILLING_MODE")
        if billing_mode == "stripe":
            if self.STRIPE_SECRET_KEY is None or _normalized_secret(self.STRIPE_SECRET_KEY) is None:
                missing.append("STRIPE_SECRET_KEY")
            if self.STRIPE_WEBHOOK_SECRET is None or _normalized_secret(self.STRIPE_WEBHOOK_SECRET) is None:
                missing.append("STRIPE_WEBHOOK_SECRET")
            if _missing_string(self.STRIPE_PRICE_ID):
                missing.append("STRIPE_PRICE_ID")

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
    """Resolve a tenant confidence threshold or fail hard if it is missing."""

    if tenant_document is None:
        raise ValueError("tenant document missing")

    tenant_settings = tenant_document.get("settings")
    if not isinstance(tenant_settings, Mapping):
        raise ValueError("tenant settings missing")

    threshold = tenant_settings.get("confidenceThreshold")
    if threshold is None:
        raise ValueError("tenant confidenceThreshold missing")

    return float(threshold)


def get_dashboard_cors_origins(runtime_settings: Settings) -> list[str]:
    """Resolve explicit dashboard CORS origins from settings."""

    candidates: list[str] = []
    if runtime_settings.DASHBOARD_APP_URL is not None:
        candidates.append(runtime_settings.DASHBOARD_APP_URL)
    if runtime_settings.DASHBOARD_CORS_ORIGINS is not None:
        candidates.extend(runtime_settings.DASHBOARD_CORS_ORIGINS.split(","))

    origins: list[str] = []
    for candidate in candidates:
        normalized = candidate.strip().rstrip("/")
        if normalized and normalized not in origins:
            origins.append(normalized)

    return origins


def get_tenant_brand_voice(
    tenant_document: Mapping[str, Any] | None,
) -> str | None:
    """Resolve an optional tenant brand voice into a prompt-safe string."""

    if tenant_document is None:
        return None

    brand_voice = tenant_document.get("brandVoice")
    if brand_voice is None:
        return None

    if isinstance(brand_voice, str):
        normalized = brand_voice.strip()
        return normalized or None

    if isinstance(brand_voice, Mapping):
        sections: list[str] = []
        for key, value in brand_voice.items():
            label = str(key).strip()
            if not label:
                continue
            if isinstance(value, str):
                normalized_value = value.strip()
                if normalized_value:
                    sections.append(f"{label}: {normalized_value}")
                continue
            if isinstance(value, (list, tuple)):
                normalized_items = [
                    str(item).strip()
                    for item in value
                    if str(item).strip()
                ]
                if normalized_items:
                    sections.append(f"{label}: {', '.join(normalized_items)}")
                continue
            if value is not None:
                normalized_value = str(value).strip()
                if normalized_value:
                    sections.append(f"{label}: {normalized_value}")

        return "\n".join(sections) if sections else None

    normalized = str(brand_voice).strip()
    return normalized or None


settings = get_settings()
