"""Smoke tests for shared pytest fixtures."""

from __future__ import annotations

from unittest.mock import AsyncMock

from svmp_core.models import GovernanceDecision


def test_shared_model_fixtures_are_representative(
    identity_frame,
    webhook_payload,
    session_state,
    knowledge_entry,
    governance_log,
) -> None:
    """Shared model fixtures should reflect the canonical test domain."""

    assert identity_frame.tenant_id == "Niyomilan"
    assert webhook_payload.client_id == "whatsapp"
    assert session_state.id == "session-1"
    assert knowledge_entry.domain_id == "general"
    assert governance_log.decision == GovernanceDecision.ANSWERED


def test_mock_database_fixture_wires_all_repository_surfaces(mock_database) -> None:
    """The shared mock database should expose async-capable repository mocks."""

    assert isinstance(mock_database.session_state, AsyncMock)
    assert isinstance(mock_database.knowledge_base, AsyncMock)
    assert isinstance(mock_database.governance_logs, AsyncMock)
    assert isinstance(mock_database.tenants, AsyncMock)
