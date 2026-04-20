"""Dashboard auth, tenant, role, and subscription context helpers."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Any

import httpx
import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from svmp_core.config import Settings, get_settings
from svmp_core.exceptions import ValidationError

_JWKS_CACHE_TTL_SECONDS = 300
_jwks_cache: dict[str, tuple[float, Mapping[str, Any]]] = {}
_ALLOWED_CLERK_JWT_ALGORITHMS = frozenset({"RS256"})


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
    organization_id: str | None = None
    auth_provider: str = "clerk"
    email: str | None = None
    claims: dict[str, Any] = Field(default_factory=dict)


class TenantContext(BaseModel):
    """Resolved dashboard tenant boundary for one authenticated request."""

    model_config = ConfigDict(frozen=True)

    user_id: str
    organization_id: str | None = None
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
    if normalized_user_id is None:
        raise ValidationError("trusted dashboard auth headers are missing")

    return AuthenticatedUser(
        user_id=normalized_user_id,
        organization_id=normalized_organization_id,
        auth_provider="trusted_headers",
        email=_non_blank(email),
    )


def _bearer_token(authorization: str | None) -> str | None:
    """Extract a bearer token from an Authorization header."""

    normalized = _non_blank(authorization)
    if normalized is None:
        return None
    scheme, _, token = normalized.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def _fetch_jwks(jwks_url: str) -> Mapping[str, Any]:
    """Fetch and cache a JWKS document."""

    cached = _jwks_cache.get(jwks_url)
    now = time.time()
    if cached is not None:
        expires_at, jwks = cached
        if expires_at > now:
            return jwks

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(jwks_url)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="failed to fetch Clerk JWKS",
        ) from exc
    if response.is_error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="failed to fetch Clerk JWKS",
        )
    try:
        jwks = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Clerk JWKS is invalid",
        ) from exc
    if not isinstance(jwks, Mapping) or not isinstance(jwks.get("keys"), list):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Clerk JWKS is invalid",
        )

    _jwks_cache[jwks_url] = (now + _JWKS_CACHE_TTL_SECONDS, jwks)
    return jwks


async def authenticated_user_from_clerk_jwt(
    token: str,
    *,
    settings: Settings,
) -> AuthenticatedUser:
    """Verify a Clerk JWT and return the dashboard user identity."""

    if settings.CLERK_ISSUER is None or not settings.CLERK_ISSUER.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Clerk issuer is not configured",
        )
    if settings.CLERK_JWKS_URL is None or not settings.CLERK_JWKS_URL.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Clerk JWKS URL is not configured",
        )

    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid Clerk token",
        ) from exc

    kid = header.get("kid")
    algorithm = header.get("alg")
    if not isinstance(kid, str) or not isinstance(algorithm, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid Clerk token header",
        )
    if algorithm not in _ALLOWED_CLERK_JWT_ALGORITHMS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unsupported Clerk token algorithm",
        )

    jwks = await _fetch_jwks(settings.CLERK_JWKS_URL.strip())
    key_data = next(
        (
            key
            for key in jwks["keys"]
            if isinstance(key, Mapping) and key.get("kid") == kid
        ),
        None,
    )
    if key_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clerk token key is unknown",
        )

    try:
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(dict(key_data)))
    except jwt.InvalidKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid Clerk token key",
        ) from exc
    try:
        claims = jwt.decode(
            token,
            public_key,
            algorithms=list(_ALLOWED_CLERK_JWT_ALGORITHMS),
            audience=settings.CLERK_AUDIENCE if settings.CLERK_AUDIENCE else None,
            issuer=settings.CLERK_ISSUER.strip(),
            options={
                "require": ["exp", "iat", "iss", "sub"],
                "verify_aud": bool(settings.CLERK_AUDIENCE),
            },
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid Clerk token",
        ) from exc

    if not isinstance(claims, Mapping):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid Clerk token claims",
        )

    user_id = _non_blank(claims.get("sub"))
    organization_id = _non_blank(claims.get("org_id"))
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clerk token missing user id",
        )

    return AuthenticatedUser(
        user_id=user_id,
        organization_id=organization_id,
        auth_provider="clerk",
        email=_non_blank(claims.get("email"))
        or _non_blank(claims.get("primary_email_address")),
        claims=dict(claims),
    )


def tenant_context_from_record(
    user: AuthenticatedUser,
    record: Mapping[str, Any],
) -> TenantContext:
    """Build a tenant context from a backend-owned verified user record."""

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
        organization_id=user.organization_id
        or _non_blank(record.get("organizationId"))
        or _non_blank(record.get("clerkOrganizationId"))
        or tenant_id,
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
        token = _bearer_token(authorization)
        if token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing authorization header",
            )
        return await authenticated_user_from_clerk_jwt(
            token,
            settings=runtime_settings,
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
        auth_provider=user.auth_provider,
        provider_user_id=user.user_id,
        email=user.email,
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

    allowed = frozenset(
        _coerce_role(role.value if isinstance(role, PortalRole) else role)
        for role in allowed_roles
    )

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
