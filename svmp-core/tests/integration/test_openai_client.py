"""Integration-style tests for the centralized OpenAI wrapper."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from svmp_core.config import Settings
from svmp_core.exceptions import IntegrationError
from svmp_core.integrations.openai_client import (
    clear_openai_client_cache,
    embed_text,
    generate_completion,
    get_openai_client,
)


def _settings() -> Settings:
    """Return deterministic OpenAI settings for tests."""

    return Settings(
        _env_file=None,
        OPENAI_API_KEY="test-key",
        EMBEDDING_MODEL="text-embedding-3-small",
        LLM_MODEL="gpt-4o-mini",
    )


@pytest.fixture(autouse=True)
def clear_cache_between_tests() -> None:
    """Reset the cached client so tests remain isolated."""

    clear_openai_client_cache()


def test_get_openai_client_caches_single_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Client creation should happen once per process unless reset."""

    created: list[str] = []

    class FakeAsyncOpenAI:
        def __init__(self, *, api_key: str) -> None:
            created.append(api_key)

    monkeypatch.setattr("svmp_core.integrations.openai_client.AsyncOpenAI", FakeAsyncOpenAI)

    first = get_openai_client(settings=_settings())
    second = get_openai_client(settings=_settings())

    assert first is second
    assert created == ["test-key"]


@pytest.mark.asyncio
async def test_embed_text_uses_embedding_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Embedding calls should route through the wrapper with configured model."""

    fake_client = Mock()
    fake_client.embeddings = Mock()
    fake_client.embeddings.create = AsyncMock(
        return_value=SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])]
        )
    )

    monkeypatch.setattr(
        "svmp_core.integrations.openai_client.get_openai_client",
        lambda settings=None: fake_client,
    )

    embedding = await embed_text("hello world", settings=_settings())

    assert embedding == [0.1, 0.2, 0.3]
    fake_client.embeddings.create.assert_awaited_once_with(
        model="text-embedding-3-small",
        input="hello world",
    )


@pytest.mark.asyncio
async def test_generate_completion_uses_chat_completions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Completion calls should route through the wrapper with configured model."""

    fake_client = Mock()
    fake_client.chat = Mock()
    fake_client.chat.completions = Mock()
    fake_client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="We help customers."))]
        )
    )

    monkeypatch.setattr(
        "svmp_core.integrations.openai_client.get_openai_client",
        lambda settings=None: fake_client,
    )

    content = await generate_completion(
        system_prompt="You are helpful.",
        user_prompt="What do you do?",
        settings=_settings(),
    )

    assert content == "We help customers."
    fake_client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_openai_wrapper_rejects_invalid_input() -> None:
    """Blank input should fail before any client call happens."""

    with pytest.raises(IntegrationError, match="embedding input must not be blank"):
        await embed_text("   ", settings=_settings())

    with pytest.raises(IntegrationError, match="system prompt must not be blank"):
        await generate_completion(
            system_prompt="   ",
            user_prompt="hello",
            settings=_settings(),
        )
