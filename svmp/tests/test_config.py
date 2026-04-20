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
    """Settings expose the expected Mongo-first defaults."""

    loaded = Settings(_env_file=None)

    assert loaded.APP_NAME == "SVMP"
    assert loaded.APP_ENV == "development"
    assert loaded.MONGODB_DB_NAME == "svmp"
    assert loaded.MONGODB_SESSION_COLLECTION == "session_state"
    assert loaded.MONGODB_KB_COLLECTION == "knowledge_base"
    assert loaded.MONGODB_GOVERNANCE_COLLECTION == "governance_logs"
    assert loaded.MONGODB_TENANTS_COLLECTION == "tenants"
    assert loaded.MONGODB_VERIFIED_USERS_COLLECTION == "verified_users"
    assert loaded.MONGODB_BILLING_SUBSCRIPTIONS_COLLECTION == "billing_subscriptions"
    assert loaded.MONGODB_INTEGRATION_STATUS_COLLECTION == "integration_status"
    assert loaded.MONGODB_AUDIT_LOGS_COLLECTION == "audit_logs"
    assert loaded.MONGODB_PROVIDER_EVENTS_COLLECTION == "provider_events"
    assert loaded.SHARED_KB_TENANT_ID == "__shared__"
    assert loaded.DEBOUNCE_MS == 2500
    assert loaded.SIMILARITY_THRESHOLD == pytest.approx(0.75)
    assert loaded.WORKFLOW_B_INTERVAL_SECONDS == 1
    assert loaded.WORKFLOW_B_PROCESSING_LOCK_TIMEOUT_SECONDS == 300
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
    assert loaded.CLERK_ISSUER is None
    assert loaded.CLERK_JWKS_URL is None
    assert loaded.CLERK_AUDIENCE is None
    assert loaded.DASHBOARD_APP_URL is None
    assert loaded.DASHBOARD_CORS_ORIGINS is None
    assert loaded.STRIPE_SECRET_KEY is None
    assert loaded.STRIPE_WEBHOOK_SECRET is None
    assert loaded.STRIPE_PRICE_ID is None
    assert loaded.BILLING_MODE == "manual"


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variables override settings defaults."""

    monkeypatch.setenv("APP_NAME", "SVMP-Test")
    monkeypatch.setenv("MONGODB_DB_NAME", "svmp_test")
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
    assert loaded.MONGODB_DB_NAME == "svmp_test"
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


def test_validate_runtime_requires_meta_values() -> None:
    """Meta mode should require the configured WhatsApp credentials."""

    settings = Settings(
        _env_file=None,
        MONGODB_URI="mongodb://unit-test",
        OPENAI_API_KEY="test-key",
    )

    with pytest.raises(ConfigError, match="WHATSAPP_PHONE_NUMBER_ID"):
        settings.validate_runtime()


def test_validate_runtime_accepts_twilio_values() -> None:
    """Twilio mode should validate against Twilio-specific credentials only."""

    settings = Settings(
        _env_file=None,
        MONGODB_URI="mongodb://unit-test",
        OPENAI_API_KEY="test-key",
        WHATSAPP_PROVIDER="twilio",
        TWILIO_ACCOUNT_SID="AC123",
        TWILIO_AUTH_TOKEN="secret",
        TWILIO_WHATSAPP_NUMBER="whatsapp:+14155238886",
    )

    settings.validate_runtime()


def test_validate_runtime_accepts_twilio_and_meta_credentials_together() -> None:
    """A single runtime may carry both provider credential sets at once."""

    settings = Settings(
        _env_file=None,
        MONGODB_URI="mongodb://unit-test",
        OPENAI_API_KEY="test-key",
        WHATSAPP_PROVIDER="meta",
        WHATSAPP_TOKEN="meta-token",
        WHATSAPP_PHONE_NUMBER_ID="1234567890",
        WHATSAPP_VERIFY_TOKEN="verify-me",
        META_APP_SECRET="app-secret",
        TWILIO_ACCOUNT_SID="AC123",
        TWILIO_AUTH_TOKEN="secret",
        TWILIO_WHATSAPP_NUMBER="whatsapp:+14155238886",
    )

    settings.validate_runtime()


def test_validate_runtime_accepts_normalized_provider_with_secret() -> None:
    """Normalized provider mode should require an internal shared secret by default."""

    settings = Settings(
        _env_file=None,
        MONGODB_URI="mongodb://unit-test",
        OPENAI_API_KEY="test-key",
        WHATSAPP_PROVIDER="normalized",
        NORMALIZED_WEBHOOK_SECRET="internal-secret",
    )

    settings.validate_runtime()


def test_validate_runtime_requires_clerk_dashboard_auth_in_production() -> None:
    """Production should not boot dashboard APIs without Clerk tenant auth."""

    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        MONGODB_URI="mongodb://unit-test",
        OPENAI_API_KEY="test-key",
        WHATSAPP_PROVIDER="normalized",
        NORMALIZED_WEBHOOK_SECRET="internal-secret",
    )

    with pytest.raises(ConfigError, match="DASHBOARD_AUTH_MODE=clerk"):
        settings.validate_runtime()


def test_validate_runtime_accepts_production_clerk_dashboard_auth_with_manual_billing() -> None:
    """Manual pilot billing should not require Stripe keys."""

    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        MONGODB_URI="mongodb://unit-test",
        OPENAI_API_KEY="test-key",
        WHATSAPP_PROVIDER="normalized",
        NORMALIZED_WEBHOOK_SECRET="internal-secret",
        DASHBOARD_AUTH_MODE="clerk",
        CLERK_ISSUER="https://example.clerk.accounts.dev",
        CLERK_JWKS_URL="https://example.clerk.accounts.dev/.well-known/jwks.json",
        CLERK_AUDIENCE="svmp-dashboard",
        DASHBOARD_APP_URL="https://app.svmpsystems.com",
    )

    settings.validate_runtime()


def test_validate_runtime_requires_stripe_values_when_gateway_billing_is_enabled() -> None:
    """Stripe settings are only required when the runtime opts into Stripe billing."""

    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        MONGODB_URI="mongodb://unit-test",
        OPENAI_API_KEY="test-key",
        WHATSAPP_PROVIDER="normalized",
        NORMALIZED_WEBHOOK_SECRET="internal-secret",
        DASHBOARD_AUTH_MODE="clerk",
        CLERK_ISSUER="https://example.clerk.accounts.dev",
        CLERK_JWKS_URL="https://example.clerk.accounts.dev/.well-known/jwks.json",
        CLERK_AUDIENCE="svmp-dashboard",
        DASHBOARD_APP_URL="https://app.svmpsystems.com",
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
