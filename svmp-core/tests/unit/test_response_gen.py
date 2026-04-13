"""Unit tests for customer-facing response generation."""

from __future__ import annotations

import pytest

from svmp_core.config import Settings
from svmp_core.core import generate_customer_response
from svmp_core.exceptions import IntegrationError
from svmp_core.models import KnowledgeEntry


def _settings() -> Settings:
    """Return deterministic settings for response-generator tests."""

    return Settings(
        _env_file=None,
        OPENAI_API_KEY="test-key",
        LLM_MODEL="gpt-4.1",
    )


def _knowledge_entry() -> KnowledgeEntry:
    """Build a representative FAQ match."""

    return KnowledgeEntry(
        _id="faq-1",
        tenantId="Niyomilan",
        domainId="general",
        question="What do you guys do?",
        answer="We help businesses automate tier-1 customer support on WhatsApp.",
        tags=["about"],
    )


@pytest.mark.asyncio
async def test_generate_customer_response_uses_completion_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matched KB responses should be generated through the OpenAI wrapper."""

    captured: dict[str, str] = {}

    async def fake_generate_completion(**kwargs) -> str:
        captured.update(kwargs)
        return "We help businesses automate tier-1 customer support on WhatsApp."

    monkeypatch.setattr(
        "svmp_core.core.response_gen.generate_completion",
        fake_generate_completion,
    )

    result = await generate_customer_response(
        "What do you guys do?",
        knowledge_entry=_knowledge_entry(),
        settings=_settings(),
    )

    assert result == "We help businesses automate tier-1 customer support on WhatsApp."
    assert "trusted FAQ answer" in captured["system_prompt"]
    assert "Matched FAQ answer" in captured["user_prompt"]


@pytest.mark.asyncio
async def test_generate_customer_response_includes_brand_voice_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured tenant brand voice should be included in the rewrite prompt."""

    captured: dict[str, str] = {}

    async def fake_generate_completion(**kwargs) -> str:
        captured.update(kwargs)
        return "Warm and polished answer."

    monkeypatch.setattr(
        "svmp_core.core.response_gen.generate_completion",
        fake_generate_completion,
    )

    result = await generate_customer_response(
        "What do you guys do?",
        knowledge_entry=_knowledge_entry(),
        brand_voice="Warm, polished, and premium. Avoid slang.",
        settings=_settings(),
    )

    assert result == "Warm and polished answer."
    assert "brand voice guidance" in captured["system_prompt"]
    assert "Tenant brand voice guidance: Warm, polished, and premium. Avoid slang." in captured["user_prompt"]


@pytest.mark.asyncio
async def test_generate_customer_response_returns_no_match_fallback() -> None:
    """Missing KB matches should return a safe human-handoff fallback."""

    result = await generate_customer_response(
        "I need help with something unusual",
        knowledge_entry=None,
        settings=_settings(),
    )

    assert result == "I couldn't find a reliable answer to that just yet."


@pytest.mark.asyncio
async def test_generate_customer_response_returns_fallback_for_blank_faq_answer() -> None:
    """Blank FAQ answers should not be sent to the model."""

    blank_answer_entry = KnowledgeEntry(
        _id="faq-blank",
        tenantId="Niyomilan",
        domainId="general",
        question="What do you guys do?",
        answer="   ",
        tags=["about"],
    )

    result = await generate_customer_response(
        "What do you guys do?",
        knowledge_entry=blank_answer_entry,
        settings=_settings(),
    )

    assert result == "I couldn't find a reliable answer to that just yet."


@pytest.mark.asyncio
async def test_generate_customer_response_rejects_blank_query() -> None:
    """Blank customer questions should fail fast."""

    with pytest.raises(IntegrationError, match="query must not be blank"):
        await generate_customer_response(
            "   ",
            knowledge_entry=_knowledge_entry(),
            settings=_settings(),
        )


@pytest.mark.asyncio
async def test_generate_customer_response_wraps_completion_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI wrapper failures should be wrapped with response-generator context."""

    async def fake_generate_completion(**kwargs) -> str:
        raise IntegrationError("OpenAI completion call failed")

    monkeypatch.setattr(
        "svmp_core.core.response_gen.generate_completion",
        fake_generate_completion,
    )

    with pytest.raises(IntegrationError, match="response generation failed"):
        await generate_customer_response(
            "What do you guys do?",
            knowledge_entry=_knowledge_entry(),
            settings=_settings(),
        )
