"""Stripe billing routes for the SVMP customer portal."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from svmp_core.auth import BILLING_ROLES, TenantContext, require_role
from svmp_core.config import Settings
from svmp_core.db.base import Database

STRIPE_API_BASE = "https://api.stripe.com/v1"


def _database_from_request(request: Request) -> Database:
    return request.app.state.database


def _settings_from_request(request: Request) -> Settings:
    return request.app.state.settings


def _secret_value(secret) -> str | None:
    if secret is None:
        return None
    value = secret.get_secret_value().strip()
    return value or None


def _require_stripe_secret(settings: Settings) -> str:
    secret = _secret_value(settings.STRIPE_SECRET_KEY)
    if secret is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe secret key is not configured",
        )
    return secret


def _require_price_id(settings: Settings) -> str:
    if settings.STRIPE_PRICE_ID is None or not settings.STRIPE_PRICE_ID.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe price id is not configured",
        )
    return settings.STRIPE_PRICE_ID.strip()


def _dashboard_url(settings: Settings) -> str:
    return (settings.DASHBOARD_APP_URL or "http://localhost:3000").rstrip("/")


def _parse_stripe_signature(signature_header: str | None) -> tuple[int, list[str]]:
    if signature_header is None or not signature_header.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="missing Stripe signature",
        )

    timestamp: int | None = None
    signatures: list[str] = []
    for part in signature_header.split(","):
        key, _, value = part.partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="invalid Stripe signature timestamp",
                ) from exc
        elif key == "v1" and value:
            signatures.append(value)

    if timestamp is None or not signatures:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid Stripe signature",
        )
    return timestamp, signatures


def verify_stripe_signature(
    *,
    raw_body: bytes,
    signature_header: str | None,
    webhook_secret: str | None,
    tolerance_seconds: int = 300,
) -> None:
    """Verify Stripe's webhook signature without the stripe package."""

    if webhook_secret is None or not webhook_secret.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe webhook secret is not configured",
        )

    timestamp, signatures = _parse_stripe_signature(signature_header)
    now = int(datetime.now(timezone.utc).timestamp())
    if abs(now - timestamp) > tolerance_seconds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe signature timestamp is outside tolerance",
        )

    signed_payload = str(timestamp).encode("utf-8") + b"." + raw_body
    expected = hmac.new(
        webhook_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid Stripe signature",
        )


def _stripe_headers(secret_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


async def _stripe_post(
    path: str,
    *,
    secret_key: str,
    data: Mapping[str, Any],
) -> Mapping[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{STRIPE_API_BASE}{path}",
            headers=_stripe_headers(secret_key),
            data=data,
        )
    if response.is_error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Stripe request failed",
        )
    payload = response.json()
    if not isinstance(payload, Mapping):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Stripe returned invalid data",
        )
    return payload


def _unix_to_datetime(value: Any) -> datetime | None:
    if not isinstance(value, (int, float)):
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _stripe_object(event: Mapping[str, Any]) -> Mapping[str, Any]:
    data = event.get("data")
    if not isinstance(data, Mapping):
        return {}
    obj = data.get("object")
    return obj if isinstance(obj, Mapping) else {}


def _tenant_id_from_stripe_object(obj: Mapping[str, Any]) -> str | None:
    metadata = obj.get("metadata")
    if isinstance(metadata, Mapping):
        tenant_id = metadata.get("tenantId")
        if isinstance(tenant_id, str) and tenant_id.strip():
            return tenant_id.strip()
    client_reference_id = obj.get("client_reference_id")
    if isinstance(client_reference_id, str) and client_reference_id.strip():
        return client_reference_id.strip()
    return None


async def _apply_subscription_state(
    *,
    database: Database,
    tenant_id: str,
    stripe_customer_id: str | None,
    stripe_subscription_id: str | None,
    status_value: str,
    current_period_end: datetime | None = None,
    price_id: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "stripeCustomerId": stripe_customer_id,
        "stripeSubscriptionId": stripe_subscription_id,
        "status": status_value,
        "updatedAt": datetime.now(timezone.utc),
    }
    if current_period_end is not None:
        payload["currentPeriodEnd"] = current_period_end
    if price_id is not None:
        payload["priceId"] = price_id

    await database.billing_subscriptions.upsert_by_tenant_id(tenant_id, payload)
    await database.tenants.update_by_tenant_id(
        tenant_id,
        {
            "billing.status": status_value,
            "billing.stripeCustomerId": stripe_customer_id,
            "billing.stripeSubscriptionId": stripe_subscription_id,
        },
    )


async def _handle_checkout_completed(database: Database, obj: Mapping[str, Any]) -> str | None:
    tenant_id = _tenant_id_from_stripe_object(obj)
    if tenant_id is None:
        return None
    customer_id = obj.get("customer") if isinstance(obj.get("customer"), str) else None
    subscription_id = obj.get("subscription") if isinstance(obj.get("subscription"), str) else None
    await _apply_subscription_state(
        database=database,
        tenant_id=tenant_id,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        status_value="active",
    )
    return tenant_id


async def _handle_subscription_event(database: Database, obj: Mapping[str, Any]) -> str | None:
    tenant_id = _tenant_id_from_stripe_object(obj)
    customer_id = obj.get("customer") if isinstance(obj.get("customer"), str) else None
    subscription_id = obj.get("id") if isinstance(obj.get("id"), str) else None
    if tenant_id is None:
        existing = await database.billing_subscriptions.get_by_stripe_ids(
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
        )
        if isinstance(existing, Mapping):
            raw_tenant_id = existing.get("tenantId")
            tenant_id = raw_tenant_id if isinstance(raw_tenant_id, str) else None
    if tenant_id is None:
        return None

    items = obj.get("items")
    price_id = None
    if isinstance(items, Mapping) and isinstance(items.get("data"), list) and items["data"]:
        first_item = items["data"][0]
        if isinstance(first_item, Mapping):
            price = first_item.get("price")
            if isinstance(price, Mapping) and isinstance(price.get("id"), str):
                price_id = price["id"]

    status_value = obj.get("status") if isinstance(obj.get("status"), str) else "none"
    await _apply_subscription_state(
        database=database,
        tenant_id=tenant_id,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        status_value=status_value,
        current_period_end=_unix_to_datetime(obj.get("current_period_end")),
        price_id=price_id,
    )
    return tenant_id


async def process_stripe_event(
    *,
    database: Database,
    event: Mapping[str, Any],
    raw_body: bytes,
) -> dict[str, Any]:
    """Apply a verified Stripe event idempotently."""

    event_id = event.get("id")
    event_type = event.get("type")
    if not isinstance(event_id, str) or not isinstance(event_type, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid Stripe event",
        )

    payload_hash = hashlib.sha256(raw_body).hexdigest()
    obj = _stripe_object(event)
    tenant_id = _tenant_id_from_stripe_object(obj)
    recorded = await database.provider_events.record_once(
        provider="stripe",
        event_id=event_id,
        event_type=event_type,
        tenant_id=tenant_id,
        payload_hash=payload_hash,
    )
    if not recorded:
        return {"status": "duplicate", "eventId": event_id}

    processed_tenant_id = tenant_id
    if event_type == "checkout.session.completed":
        processed_tenant_id = await _handle_checkout_completed(database, obj)
    elif event_type.startswith("customer.subscription."):
        processed_tenant_id = await _handle_subscription_event(database, obj)

    return {
        "status": "processed",
        "eventId": event_id,
        "eventType": event_type,
        "tenantId": processed_tenant_id,
    }


def build_billing_router() -> APIRouter:
    """Build Stripe billing API routes."""

    router = APIRouter(prefix="/api/billing", tags=["billing"])

    @router.post("/create-checkout-session")
    async def create_checkout_session(
        request: Request,
        context: TenantContext = Depends(require_role(BILLING_ROLES, require_subscription=False)),
    ) -> dict[str, Any]:
        settings = _settings_from_request(request)
        database = _database_from_request(request)
        secret_key = _require_stripe_secret(settings)
        price_id = _require_price_id(settings)
        billing = await database.billing_subscriptions.get_by_tenant_id(context.tenant_id)

        data: dict[str, Any] = {
            "mode": "subscription",
            "client_reference_id": context.tenant_id,
            "success_url": f"{_dashboard_url(settings)}/dashboard?billing=success",
            "cancel_url": f"{_dashboard_url(settings)}/settings?billing=cancelled",
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "metadata[tenantId]": context.tenant_id,
            "subscription_data[metadata][tenantId]": context.tenant_id,
        }
        if isinstance(billing, Mapping) and isinstance(billing.get("stripeCustomerId"), str):
            data["customer"] = billing["stripeCustomerId"]
        elif context.email:
            data["customer_email"] = context.email

        session = await _stripe_post(
            "/checkout/sessions",
            secret_key=secret_key,
            data=data,
        )
        return {
            "id": session.get("id"),
            "url": session.get("url"),
        }

    @router.post("/create-portal-session")
    async def create_portal_session(
        request: Request,
        context: TenantContext = Depends(require_role(BILLING_ROLES, require_subscription=False)),
    ) -> dict[str, Any]:
        settings = _settings_from_request(request)
        database = _database_from_request(request)
        secret_key = _require_stripe_secret(settings)
        billing = await database.billing_subscriptions.get_by_tenant_id(context.tenant_id)
        customer_id = billing.get("stripeCustomerId") if isinstance(billing, Mapping) else None
        if not isinstance(customer_id, str) or not customer_id.strip():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="tenant has no Stripe customer yet",
            )

        session = await _stripe_post(
            "/billing_portal/sessions",
            secret_key=secret_key,
            data={
                "customer": customer_id,
                "return_url": f"{_dashboard_url(settings)}/settings/billing",
            },
        )
        return {
            "id": session.get("id"),
            "url": session.get("url"),
        }

    @router.post("/webhook")
    async def stripe_webhook(
        request: Request,
        stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    ) -> dict[str, Any]:
        settings = _settings_from_request(request)
        raw_body = await request.body()
        verify_stripe_signature(
            raw_body=raw_body,
            signature_header=stripe_signature,
            webhook_secret=_secret_value(settings.STRIPE_WEBHOOK_SECRET),
        )
        try:
            event = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stripe webhook body must be valid JSON",
            ) from exc
        if not isinstance(event, Mapping):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stripe webhook body must be an object",
            )

        return await process_stripe_event(
            database=_database_from_request(request),
            event=event,
            raw_body=raw_body,
        )

    return router
