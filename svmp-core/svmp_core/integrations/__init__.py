"""External integration wrappers used by the SVMP core."""

from svmp_core.integrations.openai_client import (
    clear_openai_client_cache,
    embed_text,
    generate_completion,
    get_openai_client,
)
from svmp_core.integrations.whatsapp_provider import (
    MetaWhatsAppProvider,
    NormalizedWhatsAppProvider,
    WhatsAppProvider,
    get_whatsapp_provider,
    is_normalized_payload,
)

__all__ = [
    "clear_openai_client_cache",
    "embed_text",
    "generate_completion",
    "get_openai_client",
    "WhatsAppProvider",
    "NormalizedWhatsAppProvider",
    "MetaWhatsAppProvider",
    "get_whatsapp_provider",
    "is_normalized_payload",
]
