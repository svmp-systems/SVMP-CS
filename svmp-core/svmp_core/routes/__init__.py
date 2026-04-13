"""HTTP routes for the SVMP core runtime."""

from svmp_core.routes.onboarding import build_onboarding_router
from svmp_core.routes.webhook import build_webhook_router

__all__ = ["build_onboarding_router", "build_webhook_router"]
