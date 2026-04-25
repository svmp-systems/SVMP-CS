"""Tests for dashboard auth and tenant-context guardrails."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import HTTPException

from svmp_core.auth import (
    AuthenticatedUser,
    PortalRole,
    SubscriptionStatus,
    TenantContext,
    authenticated_user_from_supabase_jwt,
    authenticated_user_from_trusted_headers,
    require_active_subscription,
    require_role,
    tenant_context_from_record,
)
from svmp_core.config import Settings
from svmp_core.exceptions import ValidationError


def test_authenticated_user_from_trusted_headers_requires_identity() -> None:
    """Trusted-header scaffolding should still require user identity."""

    with pytest.raises(ValidationError, match="trusted dashboard auth headers are missing"):
        authenticated_user_from_trusted_headers(
            user_id=" ",
            organization_id=None,
            email="owner@example.com",
        )


def test_authenticated_user_from_trusted_headers_normalizes_values() -> None:
    """Trusted-header mode should normalize values into an AuthenticatedUser."""

    user = authenticated_user_from_trusted_headers(
        user_id=" user_123 ",
        organization_id=" org_123 ",
        email=" owner@example.com ",
    )

    assert user.user_id == "user_123"
    assert user.organization_id == "org_123"
    assert user.auth_provider == "trusted_headers"
    assert user.email == "owner@example.com"


@pytest.mark.asyncio
async def test_authenticated_user_from_supabase_jwt_verifies_signature_and_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Supabase JWT mode should verify JWKS signature, issuer, audience, and identity claims."""

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = "test-key"
    public_jwk["alg"] = "RS256"

    async def fake_fetch_jwks(jwks_url: str):
        return {"keys": [public_jwk]}

    monkeypatch.setattr("svmp_core.auth._fetch_jwks", fake_fetch_jwks)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "user_123",
            "email": "owner@stayparfums.com",
            "app_metadata": {"organization_id": "org_123"},
            "iss": "https://project-ref.supabase.co/auth/v1",
            "aud": "authenticated",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    user = await authenticated_user_from_supabase_jwt(
        token,
        settings=Settings(
            _env_file=None,
            SUPABASE_PROJECT_URL="https://project-ref.supabase.co",
            SUPABASE_JWT_AUDIENCE="authenticated",
        ),
    )

    assert user.user_id == "user_123"
    assert user.organization_id == "org_123"
    assert user.auth_provider == "supabase"
    assert user.email == "owner@stayparfums.com"


@pytest.mark.asyncio
async def test_authenticated_user_from_supabase_jwt_allows_missing_org_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tenant memberships resolve access, so organization context is optional."""

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = "test-key"
    public_jwk["alg"] = "ES256"

    async def fake_fetch_jwks(jwks_url: str):
        return {"keys": [public_jwk]}

    monkeypatch.setattr("svmp_core.auth._fetch_jwks", fake_fetch_jwks)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "user_123",
            "iss": "https://project-ref.supabase.co/auth/v1",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        private_key,
        algorithm="ES256",
        headers={"kid": "test-key"},
    )

    user = await authenticated_user_from_supabase_jwt(
        token,
        settings=Settings(
            _env_file=None,
            SUPABASE_PROJECT_URL="https://project-ref.supabase.co",
            SUPABASE_JWT_AUDIENCE=None,
        ),
    )

    assert user.user_id == "user_123"
    assert user.organization_id is None


@pytest.mark.asyncio
async def test_authenticated_user_from_supabase_jwt_rejects_unsupported_algorithm() -> None:
    """Supabase JWT mode should only accept supported asymmetric algorithms."""

    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "user_123",
            "iss": "https://project-ref.supabase.co/auth/v1",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        "shared-secret",
        algorithm="HS256",
        headers={"kid": "test-key"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await authenticated_user_from_supabase_jwt(
            token,
            settings=Settings(
                _env_file=None,
                SUPABASE_PROJECT_URL="https://project-ref.supabase.co",
            ),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "unsupported Supabase token algorithm"


def test_tenant_context_from_record_uses_backend_owned_membership_record() -> None:
    """Tenant context should come from backend access data, not browser tenant input."""

    user = AuthenticatedUser(
        user_id="user_123",
        organization_id="org_123",
        email="owner@stayparfums.com",
    )

    context = tenant_context_from_record(
        user,
        {
            "tenantId": "stay",
            "tenantName": "Stay Parfums",
            "role": "owner",
            "billing": {"status": "active"},
        },
    )

    assert context.user_id == "user_123"
    assert context.organization_id == "org_123"
    assert context.tenant_id == "stay"
    assert context.tenant_name == "Stay Parfums"
    assert context.role == PortalRole.OWNER
    assert context.subscription_status == SubscriptionStatus.ACTIVE
    assert context.has_active_subscription is True


def test_tenant_context_from_record_defaults_unknown_role_and_subscription_safely() -> None:
    """Malformed role or subscription values should not grant access."""

    user = AuthenticatedUser(user_id="user_123")

    context = tenant_context_from_record(
        user,
        {
            "tenantId": "stay",
            "role": "superuser",
            "subscriptionStatus": "lifetime",
        },
    )

    assert context.role == PortalRole.VIEWER
    assert context.organization_id == "stay"
    assert context.subscription_status == SubscriptionStatus.NONE
    assert context.has_active_subscription is False


def test_tenant_context_from_record_requires_tenant_id() -> None:
    """Tenant resolution records must include the backend-resolved tenant id."""

    user = AuthenticatedUser(user_id="user_123", organization_id="org_123")

    with pytest.raises(ValidationError, match="tenant context missing tenantId"):
        tenant_context_from_record(user, {"role": "owner"})


@pytest.mark.asyncio
async def test_require_active_subscription_allows_active_context() -> None:
    """Active subscriptions should pass the operational-data gate."""

    context = TenantContext(
        user_id="user_123",
        organization_id="org_123",
        tenant_id="stay",
        role=PortalRole.ADMIN,
        subscription_status=SubscriptionStatus.ACTIVE,
    )

    assert await require_active_subscription(context) == context


@pytest.mark.asyncio
async def test_require_active_subscription_blocks_inactive_context() -> None:
    """Inactive subscriptions should be blocked before operational data loads."""

    context = TenantContext(
        user_id="user_123",
        organization_id="org_123",
        tenant_id="stay",
        role=PortalRole.ADMIN,
        subscription_status=SubscriptionStatus.PAST_DUE,
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_active_subscription(context)

    assert exc_info.value.status_code == 402
    assert exc_info.value.detail == "active subscription required"


@pytest.mark.asyncio
async def test_require_role_allows_matching_role() -> None:
    """Role dependencies should allow explicitly permitted roles."""

    context = TenantContext(
        user_id="user_123",
        organization_id="org_123",
        tenant_id="stay",
        role=PortalRole.OWNER,
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    dependency = require_role([PortalRole.OWNER])

    assert await dependency(context) == context


@pytest.mark.asyncio
async def test_require_role_blocks_unlisted_role() -> None:
    """Role dependencies should reject users outside the allowed set."""

    context = TenantContext(
        user_id="user_123",
        organization_id="org_123",
        tenant_id="stay",
        role=PortalRole.ANALYST,
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    dependency = require_role([PortalRole.OWNER, PortalRole.ADMIN])

    with pytest.raises(HTTPException) as exc_info:
        await dependency(context)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "insufficient dashboard role"


@pytest.mark.asyncio
async def test_require_role_can_skip_subscription_gate_for_billing_recovery() -> None:
    """Billing routes need owner role checks even when payment is inactive."""

    context = TenantContext(
        user_id="user_123",
        organization_id="org_123",
        tenant_id="stay",
        role=PortalRole.OWNER,
        subscription_status=SubscriptionStatus.PAST_DUE,
    )
    dependency = require_role([PortalRole.OWNER], require_subscription=False)

    assert await dependency(context) == context
