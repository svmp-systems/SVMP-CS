"""Sanity tests for the shared exception hierarchy."""

from __future__ import annotations

import pytest

from svmp_core.exceptions import (
    ConfigError,
    DatabaseError,
    EscalationError,
    IntegrationError,
    NotFoundError,
    RoutingError,
    SVMPError,
    ValidationError,
)


def test_exception_hierarchy() -> None:
    """All custom exceptions should inherit from the shared base error."""

    assert issubclass(ConfigError, SVMPError)
    assert issubclass(ValidationError, SVMPError)
    assert issubclass(DatabaseError, SVMPError)
    assert issubclass(IntegrationError, SVMPError)
    assert issubclass(RoutingError, SVMPError)
    assert issubclass(EscalationError, SVMPError)
    assert issubclass(NotFoundError, SVMPError)


def test_exception_message_survives_raise() -> None:
    """Custom exceptions should preserve their message when raised."""

    with pytest.raises(ValidationError, match="bad input"):
        raise ValidationError("bad input")
