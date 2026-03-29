"""Shared pytest bootstrap and reusable fixtures for svmp-core tests."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from svmp_core.core import IdentityFrame
from svmp_core.db.base import (
    Database,
    GovernanceLogRepository,
    KnowledgeBaseRepository,
    SessionStateRepository,
    TenantRepository,
)
from svmp_core.models import (
    GovernanceDecision,
    GovernanceLog,
    KnowledgeEntry,
    MessageItem,
    SessionState,
    WebhookPayload,
)


@pytest.fixture
def fixed_now() -> datetime:
    """Return a stable timestamp shared across tests."""

    return datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def identity_frame() -> IdentityFrame:
    """Return a canonical identity tuple used throughout tests."""

    return IdentityFrame(
        tenant_id="Niyomilan",
        client_id="whatsapp",
        user_id="9845891194",
    )


@pytest.fixture
def webhook_payload(identity_frame: IdentityFrame) -> WebhookPayload:
    """Return a representative inbound webhook payload."""

    return WebhookPayload(
        tenantId=identity_frame.tenant_id,
        clientId=identity_frame.client_id,
        userId=identity_frame.user_id,
        text="What do you guys do?",
    )


@pytest.fixture
def message_item(fixed_now: datetime) -> MessageItem:
    """Return a representative inbound message fragment."""

    return MessageItem(text="hi", at=fixed_now)


@pytest.fixture
def session_state(
    identity_frame: IdentityFrame,
    message_item: MessageItem,
    fixed_now: datetime,
) -> SessionState:
    """Return a representative open session-state document."""

    return SessionState(
        _id="session-1",
        tenantId=identity_frame.tenant_id,
        clientId=identity_frame.client_id,
        userId=identity_frame.user_id,
        messages=[message_item],
        createdAt=fixed_now,
        updatedAt=fixed_now,
        debounceExpiresAt=fixed_now,
    )


@pytest.fixture
def knowledge_entry(identity_frame: IdentityFrame, fixed_now: datetime) -> KnowledgeEntry:
    """Return a representative active FAQ entry."""

    return KnowledgeEntry(
        _id="faq-1",
        tenantId=identity_frame.tenant_id,
        domainId="general",
        question="What do you guys do?",
        answer="We help customers with support automation.",
        tags=["company", "faq"],
        active=True,
        createdAt=fixed_now,
        updatedAt=fixed_now,
    )


@pytest.fixture
def governance_log(identity_frame: IdentityFrame, fixed_now: datetime) -> GovernanceLog:
    """Return a representative governance audit record."""

    return GovernanceLog(
        _id="log-1",
        tenantId=identity_frame.tenant_id,
        clientId=identity_frame.client_id,
        userId=identity_frame.user_id,
        decision=GovernanceDecision.ANSWERED,
        similarityScore=0.91,
        combinedText="What do you guys do?",
        answerSupplied="We help customers with support automation.",
        timestamp=fixed_now,
        metadata={"source": "unit-test"},
    )


@pytest.fixture
def tenant_document(identity_frame: IdentityFrame) -> dict[str, object]:
    """Return a representative tenant metadata document."""

    return {
        "_id": "tenant-1",
        "tenantId": identity_frame.tenant_id,
        "tags": ["ecom"],
        "settings": {"confidenceThreshold": 0.75},
        "domains": [
            {
                "domainId": "general",
                "name": "General",
                "description": "General product questions",
            }
        ],
    }


@pytest.fixture
def mock_session_repo(session_state: SessionState) -> AsyncMock:
    """Return an async mock shaped like the session repository contract."""

    repo = AsyncMock(spec=SessionStateRepository)
    repo.get_by_identity.return_value = session_state.model_copy(deep=True)
    repo.create.return_value = session_state.model_copy(deep=True)
    repo.update_by_id.return_value = session_state.model_copy(deep=True)
    repo.acquire_ready_session.return_value = session_state.model_copy(deep=True)
    repo.delete_stale_sessions.return_value = 1
    return repo


@pytest.fixture
def mock_knowledge_repo(knowledge_entry: KnowledgeEntry) -> AsyncMock:
    """Return an async mock shaped like the knowledge repository contract."""

    repo = AsyncMock(spec=KnowledgeBaseRepository)
    repo.list_active_by_tenant_and_domain.return_value = [knowledge_entry.model_copy(deep=True)]
    return repo


@pytest.fixture
def mock_governance_repo(governance_log: GovernanceLog) -> AsyncMock:
    """Return an async mock shaped like the governance repository contract."""

    repo = AsyncMock(spec=GovernanceLogRepository)
    repo.create.return_value = governance_log.model_copy(deep=True)
    return repo


@pytest.fixture
def mock_tenant_repo(tenant_document: dict[str, object]) -> AsyncMock:
    """Return an async mock shaped like the tenant repository contract."""

    repo = AsyncMock(spec=TenantRepository)
    repo.get_by_tenant_id.return_value = dict(tenant_document)
    return repo


@pytest.fixture
def mock_database(
    mock_session_repo: AsyncMock,
    mock_knowledge_repo: AsyncMock,
    mock_governance_repo: AsyncMock,
    mock_tenant_repo: AsyncMock,
) -> Mock:
    """Return a database-shaped mock with repository attributes attached."""

    database = Mock(spec=Database)
    database.session_state = mock_session_repo
    database.knowledge_base = mock_knowledge_repo
    database.governance_logs = mock_governance_repo
    database.tenants = mock_tenant_repo
    database.connect = AsyncMock(return_value=None)
    database.disconnect = AsyncMock(return_value=None)
    return database
