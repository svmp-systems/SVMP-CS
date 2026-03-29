"""Centralized OpenAI client wrapper for embeddings and completions."""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from svmp_core.config import Settings, get_settings
from svmp_core.exceptions import IntegrationError

_client: AsyncOpenAI | None = None


def clear_openai_client_cache() -> None:
    """Reset the cached OpenAI client, mainly for tests."""

    global _client
    _client = None


def get_openai_client(*, settings: Settings | None = None) -> AsyncOpenAI:
    """Return a cached AsyncOpenAI client configured from settings."""

    global _client

    runtime_settings = settings or get_settings()
    api_key = runtime_settings.OPENAI_API_KEY

    if api_key is None:
        raise IntegrationError("OPENAI_API_KEY is not configured")

    if _client is None:
        _client = AsyncOpenAI(api_key=api_key.get_secret_value())

    return _client


async def embed_text(text: str, *, settings: Settings | None = None) -> list[float]:
    """Create an embedding for a non-blank text input."""

    normalized = text.strip()
    if not normalized:
        raise IntegrationError("embedding input must not be blank")

    runtime_settings = settings or get_settings()
    client = get_openai_client(settings=runtime_settings)

    try:
        response = await client.embeddings.create(
            model=runtime_settings.EMBEDDING_MODEL,
            input=normalized,
        )
    except Exception as exc:  # pragma: no cover - defensive wrapper
        raise IntegrationError("OpenAI embedding call failed") from exc

    return list(response.data[0].embedding)


async def generate_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    settings: Settings | None = None,
    temperature: float = 0.0,
    max_tokens: int = 300,
) -> str:
    """Generate a chat completion using the configured LLM model."""

    normalized_system = system_prompt.strip()
    normalized_user = user_prompt.strip()

    if not normalized_system:
        raise IntegrationError("system prompt must not be blank")
    if not normalized_user:
        raise IntegrationError("user prompt must not be blank")

    runtime_settings = settings or get_settings()
    client = get_openai_client(settings=runtime_settings)

    try:
        response = await client.chat.completions.create(
            model=runtime_settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": normalized_system},
                {"role": "user", "content": normalized_user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:  # pragma: no cover - defensive wrapper
        raise IntegrationError("OpenAI completion call failed") from exc

    content: Any = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise IntegrationError("OpenAI completion returned empty content")

    return content.strip()
