"""Dashboard auth, tenant, role, and subscription context helpers.

This module is intentionally a skeleton. It defines the backend boundary the
customer portal will use, while real Clerk JWT verification and Stripe billing
updates are added in later slices.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from svmp_core.config import Settings, get_settings
from svmp_core.exceptions import ValidationError


class PortalRole(StrEnum):
    """Dashboard roles supported by the customer portal."""

    OWNER = "owner"
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class SubscriptionStatus(StrEnum):
    """Subscription statuses the dashboard gate understands."""

    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    INCOMPLETE = "incomplete"
    NONE = "none"


ACTIVE_SUBSCRIPTION_STATUSES = {
    SubscriptionStatus.TRIALING,
    SubscriptionStatus.ACTIVE,
}

BILLING_ROLES = {PortalRole.OWNER}
CONFIG_WRITE_ROLES = {PortalRole.OWNER, PortalRole.ADMIN}
READ_ONLY_ROLES = {
    PortalRole.OWNER,
    PortalRole.ADMIN,
    PortalRole.ANALYST,
    PortalRole.VIEWER,
}


class AuthenticatedUser(BaseModel):
    """A verified dashboard user before tenant resolution."""

    model_config = ConfigDict(frozen=True)

    user_id: str
    organization_id: str
    email: str | None = None
    claims: dict[str, Any] = Field(default_factory=dict)


class TenantContext(BaseModel):
    """Resolved dashboard tenant boundary for one authenticated request."""

    model_config = ConfigDict(frozen=True)

    user_id: str
    organization_id: str
    tenant_id: str
    role: PortalRole
    subscription_status: SubscriptionStatus
    email: str | None = None
    tenant_name: str | None = None

    @property
    def has_active_subscription(self) -> bool:
        """Return whether operational dashboard data should be available."""

        return self.subscription_status in ACTIVE_SUBSCRIPTION_STATUSES


def _non_blank(value: Any) -> str | None:
    """Normalize a string and return None for blank or non-string values."""

    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _coerce_role(value: Any) -> PortalRole:
    """Parse a dashboard role, defaulting malformed values to viewer."""

    normalized = _non_blank(value)
    if normalized is None:
        return PortalRole.VIEWER
    try:
        return PortalRole(normalized.lower())
    except ValueError:
        return PortalRole.VIEWER


def _coerce_subscription_status(value: Any) -> SubscriptionStatus:
    """Parse subscription status, defaulting unknown values to none."""

    normalized = _non_blank(value)
    if normalized is None:
        return SubscriptionStatus.NONE
    try:
        return SubscriptionStatus(normalized.lower())
    except ValueError:
        return SubscriptionStatus.NONE


def _nested_mapping(value: Any) -> Mapping[str, Any]:
    """Return a mapping or an empty dict for non-mapping values."""

    if isinstance(value, Mapping):
        return value
    return {}


def authenticated_user_from_trusted_headers(
    *,
    user_id: str | None,
    organization_id: str | None,
    email: str | None = None,
) -> AuthenticatedUser:
    """Build a user from trusted reverse-proxy headers.

    This is only for local/staging scaffolding when
    `DASHBOARD_AUTH_MODE=trusted_headers`. Production should use Clerk JWT
    verification instead.
    """

    normalized_user_id = _non_blank(user_id)
    normalized_organization_id = _non_blank(organization_id)
    if normalized_user_id is None or normalized_organization_id is None:
        raise ValidationError("trusted dashboard auth headers are missing")

    return AuthenticatedUser(
        user_id=normalized_user_id,
        organization_id=normalized_organization_id,
        email=_non_blank(email),
    )


def tenant_context_from_record(
    user: AuthenticatedUser,
    record: Mapping[str, Any],
) -> TenantContext:
    """Build a tenant context from a backend-owned tenant membership record."""

    tenant_id = _non_blank(record.get("tenantId"))
    if tenant_id is None:
        raise ValidationError("tenant context missing tenantId")

    billing = _nested_mapping(record.get("billing"))
    subscription = _nested_mapping(record.get("subscription"))
    subscription_status = (
        record.get("subscriptionStatus")
        or billing.get("status")
        or subscription.get("status")
    )

    return TenantContext(
        user_id=user.user_id,
        organization_id=user.organization_id,
        email=user.email or _non_blank(record.get("email")),
        tenant_id=tenant_id,
        tenant_name=_non_blank(record.get("tenantName")),
        role=_coerce_role(record.get("role")),
        subscription_status=_coerce_subscription_status(subscription_status),
    )


def _settings_from_request(request: Request) -> Settings:
    """Return app settings from request state, falling back to cached settings."""

    app_state = getattr(request.app, "state", None)
    runtime_settings = getattr(app_state, "settings", None)
    if isinstance(runtime_settings, Settings):
        return runtime_settings
    return get_settings()


async def require_user(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    trusted_user_id: str | None = Header(default=None, alias="X-SVMP-User-Id"),
    trusted_user_email: str | None = Header(default=None, alias="X-SVMP-User-Email"),
    trusted_organization_id: str | None = Header(default=None, alias="X-SVMP-Organization-Id"),
) -> AuthenticatedUser:
    """Require a verified dashboard user for portal API routes."""

    runtime_settings = _settings_from_request(request)
    mode = runtime_settings.DASHBOARD_AUTH_MODE.strip().lower()

    if mode == "trusted_headers":
        try:
            return authenticated_user_from_trusted_headers(
                user_id=trusted_user_id,
                organization_id=trusted_organization_id,
                email=trusted_user_email,
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            ) from exc

    if mode == "clerk":
        if _non_blank(authorization) is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing authorization header",
            )
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Clerk dashboard auth verification is not wired yet",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="dashboard authentication is disabled",
    )


async def require_tenant_context(
    request: Request,
    user: AuthenticatedUser = Depends(require_user),
) -> TenantContext:
    """Resolve the backend-owned tenant context for a dashboard request."""

    database = getattr(getattr(request.app, "state", None), "database", None)
    tenants = getattr(database, "tenants", None)
    resolver = getattr(tenants, "resolve_dashboard_tenant_context", None)

    if not callable(resolver):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="dashboard tenant resolution is not wired yet",
        )

    record = await resolver(
        clerk_organization_id=user.organization_id,
        clerk_user_id=user.user_id,
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user is not a member of this tenant",
        )
    if not isinstance(record, Mapping):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="dashboard tenant resolver returned invalid data",
        )

    try:
        return tenant_context_from_record(user, record)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


async def require_active_subscription(
    context: TenantContext = Depends(require_tenant_context),
) -> TenantContext:
    """Require an active or trialing tenant subscription."""

    if not context.has_active_subscription:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="active subscription required",
        )
    return context


def require_role(
    allowed_roles: Iterable[PortalRole | str],
    *,
    require_subscription: bool = True,
):
    """Return a dependency that requires one of the provided dashboard roles."""

    allowed = frozenset(_coerce_role(role.value if isinstance(role, PortalRole) else role) for role in allowed_roles)

    async def active_dependency(
        context: TenantContext = Depends(require_active_subscription),
    ) -> TenantContext:
        if context.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient dashboard role",
            )
        return context

    async def tenant_dependency(
        context: TenantContext = Depends(require_tenant_context),
    ) -> TenantContext:
        if context.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient dashboard role",
            )
        return context

    return active_dependency if require_subscription else tenant_dependency
