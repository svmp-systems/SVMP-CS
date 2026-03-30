"""Sanity tests for application settings."""

from __future__ import annotations

import pytest

from svmp_core.config import Settings, get_tenant_confidence_threshold


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
    assert loaded.DEBOUNCE_MS == 2500
    assert loaded.SIMILARITY_THRESHOLD == pytest.approx(0.75)
    assert loaded.WORKFLOW_B_INTERVAL_SECONDS == 1
    assert loaded.WORKFLOW_C_INTERVAL_HOURS == 24
    assert loaded.EMBEDDING_MODEL == "text-embedding-3-small"
    assert loaded.LLM_MODEL == "gpt-4o-mini"
    assert loaded.USE_OPENAI_MATCHER is False
    assert loaded.OPENAI_SHADOW_MODE is False
    assert loaded.OPENAI_MATCHER_CANDIDATE_LIMIT == 8


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variables override settings defaults."""

    monkeypatch.setenv("APP_NAME", "SVMP-Test")
    monkeypatch.setenv("MONGODB_DB_NAME", "svmp_test")
    monkeypatch.setenv("DEBOUNCE_MS", "3000")
    monkeypatch.setenv("USE_OPENAI_MATCHER", "true")
    monkeypatch.setenv("OPENAI_SHADOW_MODE", "true")
    monkeypatch.setenv("OPENAI_MATCHER_CANDIDATE_LIMIT", "5")

    loaded = Settings(_env_file=None)

    assert loaded.APP_NAME == "SVMP-Test"
    assert loaded.MONGODB_DB_NAME == "svmp_test"
    assert loaded.DEBOUNCE_MS == 3000
    assert loaded.USE_OPENAI_MATCHER is True
    assert loaded.OPENAI_SHADOW_MODE is True
    assert loaded.OPENAI_MATCHER_CANDIDATE_LIMIT == 5


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
