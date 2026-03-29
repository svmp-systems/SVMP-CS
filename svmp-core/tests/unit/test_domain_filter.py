"""Unit tests for deterministic domain routing."""

from __future__ import annotations

import pytest

from svmp_core.core import choose_domain
from svmp_core.exceptions import RoutingError


def test_choose_domain_matches_using_keywords() -> None:
    """Keyword overlap should select the strongest matching domain."""

    domains = [
        {
            "domainId": "sales",
            "name": "Sales",
            "description": "Pricing, discounts, and product questions",
            "keywords": ["price", "pricing", "discount", "product"],
        },
        {
            "domainId": "general",
            "name": "General",
            "description": "Company background and contact details",
            "keywords": ["about", "company", "contact"],
        },
    ]

    selected = choose_domain("Do you have any pricing discounts?", domains)

    assert selected == "sales"


def test_choose_domain_uses_fallback_when_no_keywords_match() -> None:
    """Fallback should be used when deterministic routing has no winner."""

    domains = [
        {
            "domainId": "sales",
            "name": "Sales",
            "description": "Pricing and discounts",
        }
    ]

    selected = choose_domain("hello there", domains, fallback_domain_id="general")

    assert selected == "general"


def test_choose_domain_rejects_blank_query() -> None:
    """Blank queries should fail fast instead of guessing."""

    with pytest.raises(RoutingError, match="query must not be blank"):
        choose_domain("   ", [])


def test_choose_domain_raises_when_no_match_and_no_fallback() -> None:
    """No-match cases should route to escalation logic upstream."""

    domains = [
        {
            "domainId": "sales",
            "name": "Sales",
            "description": "Pricing and discounts",
        }
    ]

    with pytest.raises(RoutingError, match="could not determine a domain"):
        choose_domain("hello there", domains)


def test_choose_domain_rejects_ambiguous_matches_without_fallback() -> None:
    """Equal-score routing ties should not be resolved arbitrarily."""

    domains = [
        {
            "domainId": "sales",
            "name": "Sales",
            "keywords": ["price"],
        },
        {
            "domainId": "support",
            "name": "Support",
            "keywords": ["price"],
        },
    ]

    with pytest.raises(RoutingError, match="safely"):
        choose_domain("price", domains)


def test_choose_domain_uses_fallback_for_ambiguous_matches() -> None:
    """Fallback should be preferred over arbitrary tie-breaking."""

    domains = [
        {
            "domainId": "sales",
            "name": "Sales",
            "keywords": ["price"],
        },
        {
            "domainId": "support",
            "name": "Support",
            "keywords": ["price"],
        },
    ]

    selected = choose_domain("price", domains, fallback_domain_id="general")

    assert selected == "general"
