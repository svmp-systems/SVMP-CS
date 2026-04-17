"""HTTP routes for the SVMP runtime."""

from svmp_core.routes.billing import build_billing_router
from svmp_core.routes.dashboard import build_dashboard_router
from svmp_core.routes.webhook import build_webhook_router

__all__ = ["build_billing_router", "build_dashboard_router", "build_webhook_router"]
