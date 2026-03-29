"""Intent routing helpers for deciding answer-vs-action behavior."""

from __future__ import annotations

from enum import StrEnum

from svmp_core.exceptions import RoutingError


class IntentType(StrEnum):
    """Supported high-level intent branches for Workflow B."""

    INFORMATIONAL = "informational"
    TRANSACTIONAL = "transactional"
    ESCALATE = "escalate"


_TRANSACTIONAL_KEYWORDS = {
    "cancel",
    "change",
    "exchange",
    "refund",
    "replace",
    "reschedule",
    "return",
    "track",
    "update",
}

_INFORMATIONAL_KEYWORDS = {
    "about",
    "contact",
    "do",
    "hours",
    "how",
    "policy",
    "price",
    "pricing",
    "ship",
    "shipping",
    "what",
    "when",
    "where",
}


def infer_intent(query: str) -> IntentType:
    """Classify a query into a safe high-level intent branch."""

    normalized = query.strip().lower()
    if not normalized:
        raise RoutingError("query must not be blank")

    tokens = set(normalized.replace("?", " ").replace(",", " ").split())
    transactional_score = len(tokens & _TRANSACTIONAL_KEYWORDS)
    informational_score = len(tokens & _INFORMATIONAL_KEYWORDS)

    if transactional_score > informational_score:
        return IntentType.TRANSACTIONAL

    if informational_score > 0:
        return IntentType.INFORMATIONAL

    return IntentType.ESCALATE
