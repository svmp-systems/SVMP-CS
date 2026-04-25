"""Sanity tests for application settings."""

from __future__ import annotations

import pytest

from svmp_core.config import (
    Settings,
    get_dashboard_cors_origins,
    get_tenant_brand_voice,
    get_tenant_confidence_threshold,
)
from svmp_core.exceptions import ConfigError


def test_settings_defaults_load() -> None:
    """Settings expose the expected Supabase/Vercel defaults."""

    loaded = Settings(_env_file=None)

    assert loaded.APP_NAME == "SVMP"
    assert loaded.APP_ENV == "development"
    assert loaded.DATABASE_URL is None
    assert loaded.SHARED_KB_TENANT_ID == "__shared__"
    assert loaded.DEBOUNCE_MS == 2500
    assert loaded.SIMILARITY_THRESHOLD == pytest.approx(0.75)
    assert loaded.WORKFLOW_B_INTERVAL_SECONDS == 1
    assert loaded.WORKFLOW_B_PROCESSING_LOCK_TIMEOUT_SECONDS == 300
    assert loaded.WORKFLOW_B_MAX_BATCH_SIZE == 25
    assert loaded.WORKFLOW_C_INTERVAL_HOURS == 24
    assert loaded.EMBEDDING_MODEL == "text-embedding-3-small"
    assert loaded.LLM_MODEL == "gpt-4.1"
    assert loaded.USE_OPENAI_MATCHER is False
    assert loaded.OPENAI_SHADOW_MODE is False
    assert loaded.OPENAI_MATCHER_CANDIDATE_LIMIT == 8
    assert loaded.WHATSAPP_PROVIDER == "meta"
    assert loaded.WEBHOOK_PUBLIC_BASE_URL is None
    assert loaded.ALLOW_NORMALIZED_WEBHOOKS is False
    assert loaded.DASHBOARD_AUTH_MODE == "disabled"
    assert loaded.SUPABASE_PROJECT_URL is None
    assert loaded.SUPABASE_JWT_ISSUER is None
    assert loaded.SUPABASE_JWKS_URL is None
    assert loaded.SUPABASE_JWT_AUDIENCE == "authenticated"
    assert loaded.DASHBOARD_APP_URL is None
    assert loaded.DASHBOARD_CORS_ORIGINS is None
    assert loaded.INTERNAL_JOB_SECRET is None
    assert loaded.CRON_SECRET is None
    assert loaded.STRIPE_SECRET_KEY is None
    assert loaded.STRIPE_WEBHOOK_SECRET is None
    assert loaded.STRIPE_PRICE_ID is None
    assert loaded.BILLING_MODE == "manual"


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variables override settings defaults."""

    monkeypatch.setenv("APP_NAME", "SVMP-Test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.test/postgres")
    monkeypatch.setenv("DEBOUNCE_MS", "3000")
    monkeypatch.setenv("USE_OPENAI_MATCHER", "true")
    monkeypatch.setenv("OPENAI_SHADOW_MODE", "true")
    monkeypatch.setenv("OPENAI_MATCHER_CANDIDATE_LIMIT", "5")
    monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

    loaded = Settings(_env_file=None)

    assert loaded.APP_NAME == "SVMP-Test"
    assert loaded.DATABASE_URL == "postgresql://example.test/postgres"
    assert loaded.DEBOUNCE_MS == 3000
    assert loaded.USE_OPENAI_MATCHER is True
    assert loaded.OPENAI_SHADOW_MODE is True
    assert loaded.OPENAI_MATCHER_CANDIDATE_LIMIT == 5
    assert loaded.WHATSAPP_PROVIDER == "twilio"
    assert loaded.TWILIO_ACCOUNT_SID == "AC123"
    assert loaded.TWILIO_WHATSAPP_NUMBER == "whatsapp:+14155238886"


def test_dashboard_cors_origins_are_normalized_and_deduplicated() -> None:
    """Dashboard CORS origins should come from explicit dashboard settings."""

    loaded = Settings(
        _env_file=None,
        DASHBOARD_APP_URL="https://app.svmpsystems.com/",
        DASHBOARD_CORS_ORIGINS=" https://app.svmpsystems.com, http://localhost:3000/ ",
    )

    assert get_dashboard_cors_origins(loaded) == [
        "https://app.svmpsystems.com",
        "http://localhost:3000",
    ]


def test_supabase_auth_helpers_derive_defaults_from_project_url() -> None:
    """Issuer and JWKS should derive from the Supabase project URL when omitted."""

    settings = Settings(
        _env_file=None,
        SUPABASE_PROJECT_URL="https://project-ref.supabase.co",
    )

    assert settings.supabase_auth_issuer() == "https://project-ref.supabase.co/auth/v1"
    assert settings.supabase_jwks_url() == "https://project-ref.supabase.co/auth/v1/.well-known/jwks.json"


def test_internal_job_secret_prefers_internal_secret_and_falls_back_to_cron_secret() -> None:
    """Internal routes should work with either dedicated or Vercel cron secrets."""

    from_internal_secret = Settings(_env_file=None, INTERNAL_JOB_SECRET="internal-secret")
    from_cron_secret = Settings(_env_file=None, CRON_SECRET="cron-secret")

    assert from_internal_secret.internal_job_secret() == "internal-secret"
    assert from_cron_secret.internal_job_secret() == "cron-secret"


def test_validate_runtime_requires_meta_values() -> None:
    """Meta mode should require the configured WhatsApp credentials."""

    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql://unit-test/postgres",
        OPENAI_API_KEY="test-key",
    )

    with pytest.raises(ConfigError, match="WHATSAPP_PHONE_NUMBER_ID"):
        settings.validate_runtime()


def test_validate_runtime_accepts_twilio_values() -> None:
    """Twilio mode should validate against Twilio-specific credentials only."""

    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql://unit-test/postgres",
        OPENAI_API_KEY="test-key",
        WHATSAPP_PROVIDER="twilio",
        TWILIO_ACCOUNT_SID="AC123",
        TWILIO_AUTH_TOKEN="secret",
        TWILIO_WHATSAPP_NUMBER="whatsapp:+14155238886",
    )

    settings.validate_runtime()


def test_validate_runtime_accepts_normalized_provider_with_secret() -> None:
    """Normalized provider mode should require an internal shared secret by default."""

    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql://unit-test/postgres",
        OPENAI_API_KEY="test-key",
        WHATSAPP_PROVIDER="normalized",
        NORMALIZED_WEBHOOK_SECRET="internal-secret",
    )

    settings.validate_runtime()


def test_validate_runtime_requires_supabase_dashboard_auth_in_production() -> None:
    """Production should not boot dashboard APIs without Supabase tenant auth."""

    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        DATABASE_URL="postgresql://unit-test/postgres",
        OPENAI_API_KEY="test-key",
        WHATSAPP_PROVIDER="normalized",
        NORMALIZED_WEBHOOK_SECRET="internal-secret",
    )

    with pytest.raises(ConfigError, match="DASHBOARD_AUTH_MODE=supabase"):
        settings.validate_runtime()


def test_validate_runtime_accepts_production_supabase_dashboard_auth_with_vercel_cron_secret() -> None:
    """Vercel cron can satisfy internal job auth without a separate secret."""

    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        DATABASE_URL="postgresql://unit-test/postgres",
        OPENAI_API_KEY="test-key",
        WHATSAPP_PROVIDER="normalized",
        NORMALIZED_WEBHOOK_SECRET="internal-secret",
        DASHBOARD_AUTH_MODE="supabase",
        DASHBOARD_APP_URL="https://app.svmpsystems.com",
        SUPABASE_PROJECT_URL="https://project-ref.supabase.co",
        CRON_SECRET="cron-secret",
    )

    settings.validate_runtime()


def test_validate_runtime_requires_internal_job_secret_or_cron_secret_in_production() -> None:
    """Production should not expose internal cron routes without shared authentication."""

    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        DATABASE_URL="postgresql://unit-test/postgres",
        OPENAI_API_KEY="test-key",
        WHATSAPP_PROVIDER="normalized",
        NORMALIZED_WEBHOOK_SECRET="internal-secret",
        DASHBOARD_AUTH_MODE="supabase",
        DASHBOARD_APP_URL="https://app.svmpsystems.com",
        SUPABASE_PROJECT_URL="https://project-ref.supabase.co",
    )

    with pytest.raises(ConfigError, match="INTERNAL_JOB_SECRET or CRON_SECRET"):
        settings.validate_runtime()


def test_validate_runtime_requires_stripe_values_when_gateway_billing_is_enabled() -> None:
    """Stripe settings are only required when the runtime opts into Stripe billing."""

    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        DATABASE_URL="postgresql://unit-test/postgres",
        OPENAI_API_KEY="test-key",
        WHATSAPP_PROVIDER="normalized",
        NORMALIZED_WEBHOOK_SECRET="internal-secret",
        DASHBOARD_AUTH_MODE="supabase",
        DASHBOARD_APP_URL="https://app.svmpsystems.com",
        SUPABASE_PROJECT_URL="https://project-ref.supabase.co",
        INTERNAL_JOB_SECRET="cron-secret",
        BILLING_MODE="stripe",
    )

    with pytest.raises(ConfigError, match="STRIPE_SECRET_KEY"):
        settings.validate_runtime()


def test_tenant_threshold_uses_tenant_value() -> None:
    """Tenant threshold resolves from tenant settings."""

    tenant_document = {"settings": {"confidenceThreshold": 0.82}}

    threshold = get_tenant_confidence_threshold(tenant_document)

    assert threshold == pytest.approx(0.82)


def test_tenant_threshold_missing_settings_fails_hard() -> None:
    """Missing tenant settings should fail hard so callers can escalate."""

    with pytest.raises(ValueError, match="tenant settings missing"):
        get_tenant_confidence_threshold({"tenantId": "Niyomilan"})


def test_tenant_threshold_missing_value_fails_hard() -> None:
    """Missing tenant confidence threshold should fail hard."""

    with pytest.raises(ValueError, match="tenant confidenceThreshold missing"):
        get_tenant_confidence_threshold({"settings": {}})


def test_tenant_brand_voice_uses_string_value() -> None:
    """Tenant brand voice should resolve from a simple configured string."""

    brand_voice = get_tenant_brand_voice(
        {"brandVoice": "Warm, polished, concise, and premium."}
    )

    assert brand_voice == "Warm, polished, concise, and premium."


def test_tenant_brand_voice_formats_mapping_value() -> None:
    """Structured brand voice config should flatten into prompt-safe guidance."""

    brand_voice = get_tenant_brand_voice(
        {
            "brandVoice": {
                "tone": "Warm and premium",
                "do": ["Be concise", "Sound confident"],
                "dont": ["Use slang"],
            }
        }
    )

    assert brand_voice == (
        "tone: Warm and premium\n"
        "do: Be concise, Sound confident\n"
        "dont: Use slang"
    )
