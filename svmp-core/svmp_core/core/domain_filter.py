"""Deterministic domain routing helpers for Workflow B."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from svmp_core.exceptions import RoutingError


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _normalize_text(value: str) -> str:
    """Lowercase and trim free text for keyword matching."""

    return value.strip().lower()


def _tokenize(value: str) -> set[str]:
    """Split text into comparable lowercase tokens."""

    return set(_TOKEN_PATTERN.findall(_normalize_text(value)))


def _domain_keywords(domain: Mapping[str, Any]) -> set[str]:
    """Extract routing keywords from a domain document."""

    keywords: set[str] = set()

    for field in ("domainId", "name", "description"):
        raw_value = domain.get(field)
        if isinstance(raw_value, str):
            keywords.update(_tokenize(raw_value))

    raw_keywords = domain.get("keywords", [])
    if isinstance(raw_keywords, Sequence) and not isinstance(raw_keywords, (str, bytes, bytearray)):
        for value in raw_keywords:
            if isinstance(value, str):
                normalized = _normalize_text(value)
                if normalized:
                    keywords.add(normalized)
                    keywords.update(_tokenize(normalized))

    return keywords


def choose_domain(
    query: str,
    domains: Sequence[Mapping[str, Any]],
    *,
    fallback_domain_id: str | None = None,
) -> str:
    """Choose the best domain for a query using deterministic keyword overlap."""

    normalized_query = _normalize_text(query)
    if not normalized_query:
        raise RoutingError("query must not be blank")

    query_tokens = _tokenize(normalized_query)
    if not query_tokens:
        raise RoutingError("query must contain searchable text")

    best_domain_id: str | None = None
    best_score = 0

    for domain in domains:
        domain_id = domain.get("domainId")
        if not isinstance(domain_id, str) or not domain_id.strip():
            continue

        score = len(query_tokens & _domain_keywords(domain))
        if score > best_score:
            best_score = score
            best_domain_id = domain_id.strip()

    if best_domain_id is not None:
        return best_domain_id

    if fallback_domain_id is not None and fallback_domain_id.strip():
        return fallback_domain_id.strip()

    raise RoutingError("could not determine a domain for the query")
