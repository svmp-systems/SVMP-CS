"""Tests for Mongo-backed dashboard tenant access resolution."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import pytest

from svmp_core.db.mongo import MongoTenantRepository


class FakeCollection:
    def __init__(self, documents: list[dict[str, Any]] | None = None) -> None:
        self.documents = documents or []

    async def find_one(self, query: dict[str, Any], sort: list[tuple[str, int]] | None = None):
        matches = [document for document in self.documents if self._matches(document, query)]
        if sort:
            for field, direction in reversed(sort):
                matches.sort(key=lambda document: document.get(field), reverse=direction < 0)
        return deepcopy(matches[0]) if matches else None

    async def find_one_and_update(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        return_document=None,
    ):
        for index, document in enumerate(self.documents):
            if self._matches(document, query):
                document.update(update.get("$set", {}))
                self.documents[index] = document
                return deepcopy(document)
        return None

    @staticmethod
    def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, expected in query.items():
            value = document.get(key)
            if isinstance(expected, dict) and "$in" in expected:
                if value not in expected["$in"]:
                    return False
                continue
            if value != expected:
                return False
        return True


@pytest.mark.asyncio
async def test_resolve_dashboard_tenant_context_uses_verified_user_record() -> None:
    """Provider user ids should resolve tenant, role, and active billing state."""

    repository = MongoTenantRepository(
        FakeCollection(
            [
                {
                    "tenantId": "stay",
                    "tenantName": "Stay Parfums",
                    "billing": {"status": "past_due"},
                }
            ]
        ),
        verified_users_collection=FakeCollection(
            [
                {
                    "tenantId": "stay",
                    "authProvider": "clerk",
                    "providerUserId": "user_123",
                    "email": "owner@stayparfums.com",
                    "role": "owner",
                    "permissions": ["read", "write", "admin"],
                    "status": "active",
                }
            ]
        ),
        billing_subscriptions_collection=FakeCollection(
            [
                {
                    "tenantId": "stay",
                    "status": "active",
                }
            ]
        ),
    )

    context = await repository.resolve_dashboard_tenant_context(
        auth_provider="clerk",
        provider_user_id="user_123",
        email="owner@stayparfums.com",
    )

    assert context == {
        "tenantId": "stay",
        "tenantName": "Stay Parfums",
        "role": "owner",
        "email": "owner@stayparfums.com",
        "organizationId": "stay",
        "permissions": ["read", "write", "admin"],
        "subscriptionStatus": "active",
        "billing": {"status": "past_due"},
    }


@pytest.mark.asyncio
async def test_resolve_dashboard_tenant_context_binds_email_invite_on_first_login() -> None:
    """Email invites should become active provider-bound records after first login."""

    now = datetime(2026, 4, 20, tzinfo=timezone.utc)
    verified_users = FakeCollection(
        [
            {
                "_id": "invite_1",
                "tenantId": "stay",
                "email": "owner@stayparfums.com",
                "role": "admin",
                "permissions": ["read", "write"],
                "status": "invited",
                "updatedAt": now,
            }
        ]
    )
    repository = MongoTenantRepository(
        FakeCollection(
            [
                {
                    "tenantId": "stay",
                    "tenantName": "Stay Parfums",
                    "billing": {"status": "trialing"},
                }
            ]
        ),
        verified_users_collection=verified_users,
    )

    context = await repository.resolve_dashboard_tenant_context(
        auth_provider="clerk",
        provider_user_id="user_123",
        email="OWNER@STAYPARFUMS.COM",
    )

    assert context is not None
    assert context["tenantId"] == "stay"
    assert context["role"] == "admin"
    assert context["subscriptionStatus"] == "trialing"
    assert verified_users.documents[0]["authProvider"] == "clerk"
    assert verified_users.documents[0]["providerUserId"] == "user_123"
    assert verified_users.documents[0]["status"] == "active"
    assert verified_users.documents[0]["acceptedAt"] is not None


@pytest.mark.asyncio
async def test_resolve_dashboard_tenant_context_rejects_unverified_user() -> None:
    """Users without an active or invited access record should not resolve a tenant."""

    repository = MongoTenantRepository(
        FakeCollection([{"tenantId": "stay"}]),
        verified_users_collection=FakeCollection(
            [
                {
                    "tenantId": "stay",
                    "authProvider": "clerk",
                    "providerUserId": "user_123",
                    "email": "owner@stayparfums.com",
                    "role": "owner",
                    "status": "suspended",
                }
            ]
        ),
    )

    context = await repository.resolve_dashboard_tenant_context(
        auth_provider="clerk",
        provider_user_id="user_123",
        email="owner@stayparfums.com",
    )

    assert context is None
