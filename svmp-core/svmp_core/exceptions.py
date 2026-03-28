"""Shared exception hierarchy for SVMP."""

from __future__ import annotations


class SVMPError(Exception):
    """Base exception for all SVMP-specific failures."""


class ConfigError(SVMPError):
    """Raised when required configuration is missing or malformed."""


class ValidationError(SVMPError):
    """Raised when inbound or persisted data fails validation rules."""


class DatabaseError(SVMPError):
    """Raised when a database operation fails."""


class IntegrationError(SVMPError):
    """Raised when an external integration call fails."""


class RoutingError(SVMPError):
    """Raised when domain or intent routing cannot be resolved safely."""


class EscalationError(SVMPError):
    """Raised when an escalation path cannot be completed."""


class NotFoundError(SVMPError):
    """Raised when a required entity cannot be found."""
