"""Customer-facing response generation built on top of the OpenAI wrapper."""

from __future__ import annotations

from svmp_core.config import Settings, get_settings
from svmp_core.exceptions import IntegrationError
from svmp_core.integrations import generate_completion
from svmp_core.models import KnowledgeEntry

_NO_MATCH_RESPONSE = (
    "I couldn't find a reliable answer to that just yet."
)


async def generate_customer_response(
    query: str,
    *,
    knowledge_entry: KnowledgeEntry | None,
    brand_voice: str | None = None,
    settings: Settings | None = None,
) -> str:
    """Generate a customer-facing answer from a matched KB entry when available."""

    normalized_query = query.strip()
    if not normalized_query:
        raise IntegrationError("query must not be blank")

    if knowledge_entry is None:
        return _NO_MATCH_RESPONSE

    if not knowledge_entry.answer.strip():
        return _NO_MATCH_RESPONSE

    runtime_settings = settings or get_settings()
    normalized_brand_voice = brand_voice.strip() if isinstance(brand_voice, str) else ""

    system_prompt = (
        "You are a helpful customer support assistant. "
        "Answer only using the trusted FAQ answer provided. "
        "Be concise, clear, and customer-friendly. "
        "Do not invent policies or details that are not in the FAQ answer."
    )
    if normalized_brand_voice:
        system_prompt += (
            " Adapt the final wording to the tenant's brand voice guidance while keeping the facts unchanged."
        )
    user_prompt = (
        f"Customer question: {normalized_query}\n\n"
        f"Matched FAQ question: {knowledge_entry.question}\n"
        f"Matched FAQ answer: {knowledge_entry.answer}\n\n"
        + (
            f"Tenant brand voice guidance: {normalized_brand_voice}\n\n"
            if normalized_brand_voice
            else ""
        )
        + "Write the final reply to the customer."
    )

    try:
        return await generate_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            settings=runtime_settings,
        )
    except IntegrationError as exc:
        raise IntegrationError("response generation failed") from exc
