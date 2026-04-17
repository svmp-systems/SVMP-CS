"""Sanity tests for abstract persistence contracts."""

from __future__ import annotations

import pytest

from svmp_core.db.base import (
    Database,
    GovernanceLogRepository,
    KnowledgeBaseRepository,
    SessionStateRepository,
    TenantRepository,
)


def test_repository_interfaces_are_abstract() -> None:
    """Abstract persistence contracts should not be directly instantiable."""

    with pytest.raises(TypeError):
        SessionStateRepository()

    with pytest.raises(TypeError):
        KnowledgeBaseRepository()

    with pytest.raises(TypeError):
        GovernanceLogRepository()

    with pytest.raises(TypeError):
        TenantRepository()

    with pytest.raises(TypeError):
        Database()


def test_session_state_repository_contract_is_present() -> None:
    """Session-state repository should expose the workflow-facing methods."""

    abstract_methods = SessionStateRepository.__abstractmethods__

    assert "get_by_identity" in abstract_methods
    assert "create" in abstract_methods
    assert "update_by_id" in abstract_methods
    assert "acquire_ready_session" in abstract_methods
    assert "delete_stale_sessions" in abstract_methods
    assert hasattr(SessionStateRepository, "get_by_id")


def test_other_repository_contracts_are_present() -> None:
    """KB, governance, tenant, and database contracts should expose required methods."""

    assert "list_active_by_tenant_and_domain" in KnowledgeBaseRepository.__abstractmethods__
    assert "create" in GovernanceLogRepository.__abstractmethods__
    assert "get_by_tenant_id" in TenantRepository.__abstractmethods__

    database_methods = Database.__abstractmethods__
    assert "session_state" in database_methods
    assert "knowledge_base" in database_methods
    assert "governance_logs" in database_methods
    assert "tenants" in database_methods
    assert "connect" in database_methods
    assert "disconnect" in database_methods
