"""External integration wrappers used by the SVMP core."""

from svmp_core.integrations.openai_client import (
    clear_openai_client_cache,
    embed_text,
    generate_completion,
    get_openai_client,
)

__all__ = [
    "clear_openai_client_cache",
    "embed_text",
    "generate_completion",
    "get_openai_client",
]
