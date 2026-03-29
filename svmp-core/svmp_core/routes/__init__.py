"""HTTP routes for the SVMP core runtime."""

from svmp_core.routes.webhook import build_webhook_router

__all__ = ["build_webhook_router"]
