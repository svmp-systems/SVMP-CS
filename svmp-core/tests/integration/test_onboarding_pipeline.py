"""Integration-style tests for the tenant onboarding pipeline."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import json
from typing import Any

import pytest

from svmp_core.config import Settings
from svmp_core.core.onboarding import ScrapedDocument, run_tenant_onboarding_pipeline
from svmp_core.db.base import (
    Database,
    GovernanceLogRepository,
    KnowledgeBaseRepository,
    SessionStateRepository,
    TenantRepository,
)
from svmp_core.models import GovernanceLog, KnowledgeEntry, SessionState, TenantOnboardingRequest


class InMemorySessionRepository(SessionStateRepository):
    async def get_by_identity(self, tenant_id: str, client_id: str, user_id: str) -> SessionState | None:
        return None

    async def create(self, session: SessionState) -> SessionState:
        return session

    async def update_by_id(self, session_id: str, data: Mapping[str, Any]) -> SessionState | None:
        return None

    async def acquire_ready_session(self, now: datetime) -> SessionState | None:
        return None

    async def delete_stale_sessions(self, before: datetime) -> int:
        return 0


class InMemoryKnowledgeRepository(KnowledgeBaseRepository):
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], list[KnowledgeEntry]] = {}

    async def list_active_by_tenant_and_domain(self, tenant_id: str, domain_id: str) -> list[KnowledgeEntry]:
        return [entry.model_copy(deep=True) for entry in self._entries.get((tenant_id, domain_id), [])]

    async def replace_entries_for_tenant_domain(
        self,
        tenant_id: str,
        domain_id: str,
        entries: list[KnowledgeEntry],
    ) -> int:
        self._entries[(tenant_id, domain_id)] = [entry.model_copy(deep=True) for entry in entries]
        return len(entries)


class InMemoryGovernanceRepository(GovernanceLogRepository):
    async def create(self, log: GovernanceLog) -> GovernanceLog:
        return log


class InMemoryTenantRepository(TenantRepository):
    def __init__(self) -> None:
        self._documents: dict[str, dict[str, Any]] = {}

    async def get_by_tenant_id(self, tenant_id: str) -> Mapping[str, Any] | None:
        document = self._documents.get(tenant_id)
        return deepcopy(document) if document is not None else None

    async def upsert_tenant(self, tenant_document: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = deepcopy(dict(tenant_document))
        self._documents[str(payload["tenantId"])] = payload
        return deepcopy(payload)


class InMemoryDatabase(Database):
    def __init__(self) -> None:
        self._session_state = InMemorySessionRepository()
        self._knowledge_base = InMemoryKnowledgeRepository()
        self._governance_logs = InMemoryGovernanceRepository()
        self._tenants = InMemoryTenantRepository()

    @property
    def session_state(self) -> SessionStateRepository:
        return self._session_state

    @property
    def knowledge_base(self) -> KnowledgeBaseRepository:
        return self._knowledge_base

    @property
    def governance_logs(self) -> GovernanceLogRepository:
        return self._governance_logs

    @property
    def tenants(self) -> TenantRepository:
        return self._tenants

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        OPENAI_API_KEY="test-key",
        ONBOARDING_FAQ_TARGET_COUNT=30,
    )


@pytest.mark.asyncio
async def test_onboarding_pipeline_scrapes_generates_and_seeds_kb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Onboarding should persist tenant state and replace the generated general-domain FAQ seed."""

    async def fake_scrape_website_documents(website_url: str, *, settings: Settings | None = None):
        return [
            ScrapedDocument(
                url=website_url,
                title="Stay",
                text="Stay sells premium perfumes, offers shipping, and helps customers choose fragrances.",
                source_type="website",
            )
        ]

    async def fake_scrape_public_question_documents(urls, *, settings: Settings | None = None):
        return [
            ScrapedDocument(
                url="https://www.reddit.com/r/fragrance/comments/example",
                title="Reddit thread",
                text="People ask about best sellers, longevity, and pricing.",
                source_type="public_question",
            )
        ]

    faq_payload = {
        "faqs": [
            {
                "question": f"FAQ question {index}",
                "answer": f"FAQ answer {index}",
                "tags": ["autogen", f"topic-{index}"],
            }
            for index in range(1, 11)
        ]
    }
    responses = iter(
        [
            '{"companySummary":"Stay is a premium fragrance brand.","facts":["Sells premium perfumes","Offers shipping"],"customerConcerns":["Best sellers","Longevity"],"faqAngles":["pricing","shipping","product recommendations"]}',
            json.dumps(faq_payload),
        ]
    )

    async def fake_generate_completion(**kwargs) -> str:
        return next(responses)

    monkeypatch.setattr(
        "svmp_core.core.onboarding.scrape_website_documents",
        fake_scrape_website_documents,
    )
    monkeypatch.setattr(
        "svmp_core.core.onboarding.scrape_public_question_documents",
        fake_scrape_public_question_documents,
    )
    monkeypatch.setattr(
        "svmp_core.core.onboarding.generate_completion",
        fake_generate_completion,
    )
    monkeypatch.setattr(
        "svmp_core.core.onboarding._load_materialized_shared_entries",
        lambda tenant_id, domain_id="general": [
            KnowledgeEntry(
                _id=f"shared-hi-for-{tenant_id}",
                tenantId=tenant_id,
                domainId=domain_id,
                question="Hi",
                answer="Hi! I can help with products, pricing, shipping, or support.",
                tags=["shared", "shared_seed"],
            ),
            KnowledgeEntry(
                _id=f"shared-help-for-{tenant_id}",
                tenantId=tenant_id,
                domainId=domain_id,
                question="Can you help me?",
                answer="Yes. Tell me what you need help with.",
                tags=["shared", "shared_seed"],
            ),
        ],
    )

    database = InMemoryDatabase()
    request = TenantOnboardingRequest(
        tenantId="Stay",
        websiteUrl="https://stayparfums.example",
        brandVoice="Warm, polished, and premium.",
        publicQuestionUrls=["https://www.reddit.com/r/fragrance/comments/example"],
        targetFaqCount=10,
    )

    result = await run_tenant_onboarding_pipeline(
        database,
        request,
        settings=_settings(),
    )

    assert result["written"] == 12
    assert result["sharedSeedCount"] == 2
    tenant = await database.tenants.get_by_tenant_id("Stay")
    assert tenant is not None
    assert tenant["websiteUrl"] == "https://stayparfums.example/"
    assert tenant["brandVoice"] == "Warm, polished, and premium."
    assert tenant["onboarding"]["status"] == "completed"
    assert tenant["onboarding"]["generatedFaqCountBeforeShared"] == 10
    assert tenant["onboarding"]["generatedFaqCount"] == 12
    assert tenant["onboarding"]["sharedSeedCount"] == 2
    assert tenant["domains"][0]["domainId"] == "general"

    entries = await database.knowledge_base.list_active_by_tenant_and_domain("Stay", "general")
    assert len(entries) == 12
    assert entries[0].tenant_id == "Stay"
    assert "autogenerated" in entries[0].tags
    assert any(entry.question == "Hi" for entry in entries)
