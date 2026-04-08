"""Tenant onboarding pipeline for website-driven FAQ seed generation."""

from __future__ import annotations

import json
import re
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from svmp_core.config import Settings, get_settings
from svmp_core.db.base import Database
from svmp_core.exceptions import DatabaseError, IntegrationError, ValidationError
from svmp_core.integrations import generate_completion
from svmp_core.logger import get_logger
from svmp_core.models import KnowledgeEntry, TenantOnboardingRequest

logger = get_logger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_KB_FILE = REPO_ROOT / "scripts" / "demo_data" / "shared_kb.json"


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def _strip_json_fence(value: str) -> str:
    """Remove markdown code fences around JSON responses when present."""

    normalized = value.strip()
    if normalized.startswith("```") and normalized.endswith("```"):
        lines = normalized.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return normalized


def _normalize_whitespace(value: str) -> str:
    """Collapse repeated whitespace into a prompt-safe plain-text string."""

    return re.sub(r"\s+", " ", unescape(value)).strip()


def _slugify(value: str) -> str:
    """Build a stable identifier fragment from free-form text."""

    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "item"


def _merge_tags(existing: Any, incoming: Sequence[str]) -> list[str]:
    """Merge tenant tags while keeping ordering stable and removing blanks."""

    merged: list[str] = []
    for source in (existing if isinstance(existing, list) else [], list(incoming)):
        for item in source:
            if not isinstance(item, str):
                continue
            normalized = item.strip()
            if normalized and normalized not in merged:
                merged.append(normalized)
    return merged


def _normalize_url(value: str) -> str:
    """Normalize a URL for fetch/dedup purposes."""

    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValidationError("websiteUrl must use http or https")
    normalized_path = parsed.path or "/"
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            normalized_path,
            "",
            parsed.query,
            "",
        )
    )


class _HTMLContentParser(HTMLParser):
    """Minimal HTML parser that extracts text blocks and same-page links."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.links: list[str] = []
        self._in_title = False
        self._skip_depth = 0
        self._active_tag: str | None = None
        self._buffer: list[str] = []
        self._text_blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return

        if tag == "title":
            self._in_title = True
            return

        if self._skip_depth:
            return

        if tag == "meta":
            attrs_map = {key.lower(): value for key, value in attrs if value is not None}
            if attrs_map.get("name", "").lower() == "description":
                description = _normalize_whitespace(attrs_map.get("content", ""))
                if description:
                    self._text_blocks.append(description)
            return

        if tag == "a":
            for key, value in attrs:
                if key.lower() == "href" and value:
                    self.links.append(value)
                    break

        if tag in {"h1", "h2", "h3", "p", "li"}:
            self._active_tag = tag
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return

        if tag == "title":
            self._in_title = False
            return

        if self._skip_depth:
            return

        if self._active_tag == tag:
            text = _normalize_whitespace("".join(self._buffer))
            if text:
                self._text_blocks.append(text)
            self._buffer = []
            self._active_tag = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
        elif self._active_tag is not None:
            self._buffer.append(data)

    @property
    def text(self) -> str:
        """Return the extracted text blocks as one plain-text body."""

        return "\n".join(block for block in self._text_blocks if block)


@dataclass(frozen=True)
class ScrapedDocument:
    """Plain-text representation of one fetched source document."""

    url: str
    title: str
    text: str
    source_type: str


async def _fetch_html(
    client: httpx.AsyncClient,
    url: str,
    *,
    source_type: str,
    max_chars: int,
) -> ScrapedDocument:
    response = await client.get(url)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        raise ValidationError(f"unsupported content type for onboarding fetch: {content_type or 'unknown'}")

    parser = _HTMLContentParser()
    parser.feed(response.text)
    title = _normalize_whitespace(parser.title)
    text = parser.text.strip()
    if not text:
        raise ValidationError("fetched page did not contain readable text")

    return ScrapedDocument(
        url=str(response.url),
        title=title,
        text=text[:max_chars],
        source_type=source_type,
    )


def _same_origin_link(base_url: str, candidate: str) -> str | None:
    """Resolve a candidate link and keep only same-origin HTTP(S) URLs."""

    if not candidate or candidate.startswith("#") or candidate.startswith("mailto:") or candidate.startswith("tel:"):
        return None

    try:
        resolved = _normalize_url(urljoin(base_url, candidate))
    except ValidationError:
        return None
    base = urlparse(base_url)
    target = urlparse(resolved)
    if target.netloc != base.netloc:
        return None
    return resolved


async def scrape_website_documents(
    website_url: str,
    *,
    settings: Settings | None = None,
) -> list[ScrapedDocument]:
    """Crawl a website homepage and a small same-origin page set."""

    runtime_settings = settings or get_settings()
    normalized_root = _normalize_url(website_url)
    visited: set[str] = set()
    queued: deque[str] = deque([normalized_root])
    scraped: list[ScrapedDocument] = []

    async with httpx.AsyncClient(
        timeout=runtime_settings.ONBOARDING_FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={
            "User-Agent": "SVMP-OnboardingBot/1.0 (+https://svmp.local)",
            "Accept": "text/html,application/xhtml+xml",
        },
    ) as client:
        while queued and len(scraped) < runtime_settings.ONBOARDING_MAX_SITE_PAGES:
            next_url = queued.popleft()
            if next_url in visited:
                continue
            visited.add(next_url)

            response = await client.get(next_url)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                continue

            parser = _HTMLContentParser()
            parser.feed(response.text)
            text = parser.text.strip()
            if not text:
                continue

            scraped.append(
                ScrapedDocument(
                    url=str(response.url),
                    title=_normalize_whitespace(parser.title),
                    text=text[: runtime_settings.ONBOARDING_MAX_SOURCE_CHARS_PER_PAGE],
                    source_type="website",
                )
            )

            for candidate in parser.links:
                resolved = _same_origin_link(str(response.url), candidate)
                if resolved is not None and resolved not in visited:
                    queued.append(resolved)

    return scraped


async def scrape_public_question_documents(
    urls: Sequence[str],
    *,
    settings: Settings | None = None,
) -> list[ScrapedDocument]:
    """Fetch explicitly provided public-Q&A pages such as Reddit or Quora URLs."""

    runtime_settings = settings or get_settings()
    normalized_urls: list[str] = []
    for raw_url in urls[: runtime_settings.ONBOARDING_MAX_PUBLIC_QA_URLS]:
        normalized_urls.append(_normalize_url(raw_url))

    if not normalized_urls:
        return []

    documents: list[ScrapedDocument] = []
    async with httpx.AsyncClient(
        timeout=runtime_settings.ONBOARDING_FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={
            "User-Agent": "SVMP-OnboardingBot/1.0 (+https://svmp.local)",
            "Accept": "text/html,application/xhtml+xml",
        },
    ) as client:
        for url in normalized_urls:
            try:
                documents.append(
                    await _fetch_html(
                        client,
                        url,
                        source_type="public_question",
                        max_chars=runtime_settings.ONBOARDING_MAX_SOURCE_CHARS_PER_PAGE,
                    )
                )
            except Exception:
                logger.warning("onboarding_public_source_fetch_failed", url=url)

    return documents


def _source_payload(documents: Sequence[ScrapedDocument]) -> list[dict[str, str]]:
    """Convert scraped documents into prompt-ready source payloads."""

    return [
        {
            "url": document.url,
            "title": document.title,
            "sourceType": document.source_type,
            "text": document.text,
        }
        for document in documents
    ]


def _load_materialized_shared_entries(
    tenant_id: str,
    *,
    domain_id: str = "general",
) -> list[KnowledgeEntry]:
    """Load shared filler FAQs and materialize them into a tenant-specific seed set."""

    if not SHARED_KB_FILE.exists():
        logger.warning("onboarding_shared_seed_missing", path=str(SHARED_KB_FILE))
        return []

    raw_payload = json.loads(SHARED_KB_FILE.read_text(encoding="utf-8"))
    raw_entries = raw_payload.get("entries", [])
    if not isinstance(raw_entries, list):
        return []

    shared_entries: list[KnowledgeEntry] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, Mapping):
            continue
        question = str(raw_entry.get("question", "")).strip()
        answer = str(raw_entry.get("answer", "")).strip()
        if not question or not answer:
            continue
        raw_tags = raw_entry.get("tags", [])
        tags = [
            str(tag).strip()
            for tag in raw_tags
            if isinstance(tag, str) and str(tag).strip()
        ]
        source_id = str(raw_entry.get("_id", "")).strip() or _slugify(question)
        shared_entries.append(
            KnowledgeEntry(
                _id=f"{source_id}-for-{tenant_id}",
                tenantId=tenant_id,
                domainId=domain_id,
                question=question,
                answer=answer,
                tags=sorted(set([*tags, "shared_seed"])),
                active=bool(raw_entry.get("active", True)),
            )
        )

    return shared_entries


def _merge_seed_entries(
    generated_entries: Sequence[KnowledgeEntry],
    shared_entries: Sequence[KnowledgeEntry],
) -> list[KnowledgeEntry]:
    """Merge generated and shared seed entries without duplicating questions."""

    merged: list[KnowledgeEntry] = []
    seen_questions: set[str] = set()

    for entry in [*generated_entries, *shared_entries]:
        normalized_question = entry.question.strip().lower()
        if not normalized_question or normalized_question in seen_questions:
            continue
        seen_questions.add(normalized_question)
        merged.append(entry)

    return merged


async def _build_seed_brief(
    request: TenantOnboardingRequest,
    *,
    website_documents: Sequence[ScrapedDocument],
    public_question_documents: Sequence[ScrapedDocument],
    settings: Settings,
) -> dict[str, Any]:
    """Use the LLM to distill scraped material into a compact factual brief."""

    response = await generate_completion(
        system_prompt=(
            "You are preparing source material for a customer-support knowledge base. "
            "Read the provided website and public-question documents, then return valid JSON only. "
            "Do not invent facts that are not present in the sources. "
            "Summarize products/services, policies, customer concerns, objections, and recurring questions."
        ),
        user_prompt=json.dumps(
            {
                "tenantId": request.tenant_id,
                "tenantName": request.tenant_name,
                "websiteUrl": str(request.website_url),
                "brandVoice": request.brand_voice,
                "targetFaqCount": request.target_faq_count,
                "websiteDocuments": _source_payload(website_documents),
                "publicQuestionDocuments": _source_payload(public_question_documents),
                "responseSchema": {
                    "companySummary": "string",
                    "facts": ["string"],
                    "customerConcerns": ["string"],
                    "faqAngles": ["string"],
                },
            },
            ensure_ascii=True,
        ),
        settings=settings,
        temperature=0.2,
        max_tokens=1500,
    )
    parsed = json.loads(_strip_json_fence(response))
    if not isinstance(parsed, Mapping):
        raise IntegrationError("onboarding brief generation returned invalid JSON")
    return dict(parsed)


async def _generate_faq_seed(
    request: TenantOnboardingRequest,
    *,
    seed_brief: Mapping[str, Any],
    settings: Settings,
) -> list[KnowledgeEntry]:
    """Use the LLM to synthesize a large tenant-scoped FAQ seed set."""

    response = await generate_completion(
        system_prompt=(
            "You generate high-quality tenant FAQ seeds for customer-support automation. "
            "Return valid JSON only. "
            "Use only the provided factual brief. "
            "Create a broad, practical FAQ set that covers discovery, pricing, fulfillment, product fit, policies, objections, support, and common pre-purchase questions. "
            "Answers must be concise, factual, and safe for first-line support. "
            "Respect the tenant brand voice while staying grounded in the brief."
        ),
        user_prompt=json.dumps(
            {
                "tenantId": request.tenant_id,
                "websiteUrl": str(request.website_url),
                "brandVoice": request.brand_voice,
                "targetFaqCount": request.target_faq_count,
                "domainId": "general",
                "seedBrief": seed_brief,
                "responseSchema": {
                    "faqs": [
                        {
                            "question": "string",
                            "answer": "string",
                            "tags": ["string"],
                        }
                    ]
                },
                "requirements": [
                    "Return at least the requested number of FAQs.",
                    "Keep each answer grounded in the provided brief.",
                    "Write customer-facing answers in the tenant's brand voice.",
                    "Avoid duplicate questions.",
                ],
            },
            ensure_ascii=True,
        ),
        settings=settings,
        temperature=0.3,
        max_tokens=4000,
    )
    parsed = json.loads(_strip_json_fence(response))
    if not isinstance(parsed, Mapping):
        raise IntegrationError("onboarding FAQ generation returned invalid JSON")

    raw_faqs = parsed.get("faqs")
    if not isinstance(raw_faqs, list) or not raw_faqs:
        raise IntegrationError("onboarding FAQ generation returned no FAQs")

    entries: list[KnowledgeEntry] = []
    for index, raw_entry in enumerate(raw_faqs, start=1):
        if not isinstance(raw_entry, Mapping):
            continue
        question = str(raw_entry.get("question", "")).strip()
        answer = str(raw_entry.get("answer", "")).strip()
        raw_tags = raw_entry.get("tags", [])
        if not question or not answer:
            continue
        tags = [
            str(tag).strip()
            for tag in raw_tags
            if isinstance(tag, str) and str(tag).strip()
        ]
        entries.append(
            KnowledgeEntry(
                _id=f"faq-auto-{index:02d}-{_slugify(question)[:48]}",
                tenantId=request.tenant_id,
                domainId="general",
                question=question,
                answer=answer,
                tags=sorted(set([*tags, "autogenerated", "website_onboarding"])),
            )
        )

    if len(entries) < min(10, request.target_faq_count):
        raise IntegrationError("onboarding FAQ generation returned too few valid FAQs")

    return entries


def _ensure_general_domain(
    existing_domains: Any,
    *,
    website_url: str,
) -> list[dict[str, Any]]:
    """Ensure the tenant has at least one catch-all general domain."""

    if isinstance(existing_domains, list) and existing_domains:
        return [dict(domain) for domain in existing_domains if isinstance(domain, Mapping)]

    hostname = urlparse(website_url).netloc
    return [
        {
            "domainId": "general",
            "name": "General",
            "description": f"General support and website-derived FAQs for {hostname}.",
            "keywords": ["pricing", "shipping", "products", "support", "about"],
        }
    ]


async def _merge_and_save_tenant(
    database: Database,
    tenant_id: str,
    updates: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Fetch, merge, and persist a tenant document."""

    existing = await database.tenants.get_by_tenant_id(tenant_id)
    merged: dict[str, Any] = dict(existing) if isinstance(existing, Mapping) else {"tenantId": tenant_id}
    merged.update(dict(updates))
    stored = await database.tenants.upsert_tenant(merged)
    return stored


async def run_tenant_onboarding_pipeline(
    database: Database,
    request: TenantOnboardingRequest,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run the scrape -> synthesize -> seed pipeline for one tenant."""

    runtime_settings = settings or get_settings()
    started_at = _utcnow()
    existing_tenant = await database.tenants.get_by_tenant_id(request.tenant_id)

    await _merge_and_save_tenant(
        database,
        request.tenant_id,
        {
            "tenantId": request.tenant_id,
            "tenantName": request.tenant_name,
            "websiteUrl": str(request.website_url),
            "brandVoice": request.brand_voice,
            "tags": _merge_tags(
                existing_tenant.get("tags") if isinstance(existing_tenant, Mapping) else [],
                request.tags,
            ),
            "domains": _ensure_general_domain(
                existing_tenant.get("domains") if isinstance(existing_tenant, Mapping) else None,
                website_url=str(request.website_url),
            ),
            "updatedAt": started_at,
            "onboarding": {
                "status": "processing",
                "startedAt": started_at,
                "completedAt": None,
                "lastError": None,
                "targetFaqCount": request.target_faq_count,
                "sourceWebsiteUrl": str(request.website_url),
                "publicQuestionUrls": [str(url) for url in request.public_question_urls],
            },
        },
    )

    try:
        website_documents = await scrape_website_documents(
            str(request.website_url),
            settings=runtime_settings,
        )
        if not website_documents:
            raise ValidationError("website onboarding scrape returned no readable pages")

        public_question_documents = await scrape_public_question_documents(
            [str(url) for url in request.public_question_urls],
            settings=runtime_settings,
        )
        seed_brief = await _build_seed_brief(
            request,
            website_documents=website_documents,
            public_question_documents=public_question_documents,
            settings=runtime_settings,
        )
        entries = await _generate_faq_seed(
            request,
            seed_brief=seed_brief,
            settings=runtime_settings,
        )
        shared_entries = _load_materialized_shared_entries(
            request.tenant_id,
            domain_id="general",
        )
        merged_entries = _merge_seed_entries(entries, shared_entries)
        written = await database.knowledge_base.replace_entries_for_tenant_domain(
            request.tenant_id,
            "general",
            merged_entries,
        )

        completed_at = _utcnow()
        stored_tenant = await _merge_and_save_tenant(
            database,
            request.tenant_id,
            {
                "tenantId": request.tenant_id,
                "tenantName": request.tenant_name,
                "websiteUrl": str(request.website_url),
                "brandVoice": request.brand_voice,
                "tags": _merge_tags(
                    (
                        (await database.tenants.get_by_tenant_id(request.tenant_id)) or {}
                    ).get("tags"),
                    request.tags,
                ),
                "domains": _ensure_general_domain(
                    (
                        (await database.tenants.get_by_tenant_id(request.tenant_id)) or {}
                    ).get("domains"),
                    website_url=str(request.website_url),
                ),
                "updatedAt": completed_at,
                "onboarding": {
                    "status": "completed",
                    "startedAt": started_at,
                    "completedAt": completed_at,
                    "lastError": None,
                    "targetFaqCount": request.target_faq_count,
                    "generatedFaqCountBeforeShared": len(entries),
                    "generatedFaqCount": written,
                    "sharedSeedCount": len(shared_entries),
                    "seededDomainId": "general",
                    "sourceWebsiteUrl": str(request.website_url),
                    "sourcePageCount": len(website_documents),
                    "publicQuestionSourceCount": len(public_question_documents),
                    "publicQuestionUrls": [str(url) for url in request.public_question_urls],
                },
            },
        )
        logger.info(
            "tenant_onboarding_completed",
            tenantId=request.tenant_id,
            websiteUrl=str(request.website_url),
            generatedFaqCount=written,
            sourcePageCount=len(website_documents),
            publicQuestionSourceCount=len(public_question_documents),
        )
        return {
            "tenant": stored_tenant,
            "written": written,
            "sharedSeedCount": len(shared_entries),
            "websiteDocuments": len(website_documents),
            "publicQuestionDocuments": len(public_question_documents),
        }
    except Exception as exc:
        failed_at = _utcnow()
        await _merge_and_save_tenant(
            database,
            request.tenant_id,
            {
                "tenantId": request.tenant_id,
                "tenantName": request.tenant_name,
                "websiteUrl": str(request.website_url),
                "brandVoice": request.brand_voice,
                "tags": _merge_tags(
                    (
                        (await database.tenants.get_by_tenant_id(request.tenant_id)) or {}
                    ).get("tags"),
                    request.tags,
                ),
                "domains": _ensure_general_domain(
                    (
                        (await database.tenants.get_by_tenant_id(request.tenant_id)) or {}
                    ).get("domains"),
                    website_url=str(request.website_url),
                ),
                "updatedAt": failed_at,
                "onboarding": {
                    "status": "failed",
                    "startedAt": started_at,
                    "completedAt": failed_at,
                    "lastError": str(exc),
                    "targetFaqCount": request.target_faq_count,
                    "sourceWebsiteUrl": str(request.website_url),
                    "publicQuestionUrls": [str(url) for url in request.public_question_urls],
                },
            },
        )
        logger.exception(
            "tenant_onboarding_failed",
            tenantId=request.tenant_id,
            websiteUrl=str(request.website_url),
        )
        raise
