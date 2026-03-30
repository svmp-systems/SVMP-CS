"""Webhook routes for verification and provider-agnostic inbound intake."""

from __future__ import annotations

from collections.abc import Mapping
from json import JSONDecodeError
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status

from svmp_core.config import Settings, get_settings
from svmp_core.db.base import Database
from svmp_core.exceptions import DatabaseError, ValidationError
from svmp_core.integrations import get_whatsapp_provider
from svmp_core.workflows import run_workflow_a


def build_webhook_router(
    database: Database,
    *,
    settings: Settings | None = None,
) -> APIRouter:
    """Build a webhook router bound to the provided runtime dependencies."""

    runtime_settings = settings or get_settings()
    router = APIRouter()

    def _http_400(detail: str) -> HTTPException:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    @router.get("/webhook")
    async def verify_webhook(
        hub_mode: str | None = Query(default=None, alias="hub.mode"),
        hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
        hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
        requested_provider: str | None = Query(default=None, alias="provider"),
        provider_header: str | None = Header(default=None, alias="X-SVMP-Provider"),
    ) -> Response:
        provider = get_whatsapp_provider(
            settings=runtime_settings,
            requested_provider=provider_header or requested_provider,
        )

        try:
            challenge = provider.verify_webhook(
                settings=runtime_settings,
                hub_mode=hub_mode,
                hub_verify_token=hub_verify_token,
                hub_challenge=hub_challenge,
            )
        except ValidationError as exc:
            detail = str(exc)
            if detail == "webhook verification failed":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail) from exc
            raise _http_400(detail) from exc

        if challenge is None:
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail=f"webhook verification is not supported for provider: {provider.name}",
            )

        return Response(content=challenge, media_type="text/plain")

    @router.post("/webhook")
    async def intake_webhook(
        request: Request,
        tenant_id_query: str | None = Query(default=None, alias="tenantId"),
        provider_query: str | None = Query(default=None, alias="provider"),
        tenant_id_header: str | None = Header(default=None, alias="X-SVMP-Tenant-Id"),
        provider_header: str | None = Header(default=None, alias="X-SVMP-Provider"),
    ) -> dict[str, Any]:
        resolved_tenant_id = tenant_id_header or tenant_id_query
        requested_provider = provider_header or provider_query

        try:
            raw_payload = await request.json()
            if not isinstance(raw_payload, Mapping):
                raise ValidationError("webhook payload must be a JSON object")

            provider = get_whatsapp_provider(
                settings=runtime_settings,
                requested_provider=requested_provider,
                payload=raw_payload if isinstance(raw_payload, Mapping) else None,
            )

            payloads = provider.normalize_json_payload(
                raw_payload,
                tenant_id=resolved_tenant_id,
            )
        except JSONDecodeError as exc:
            raise _http_400("webhook payload must be valid JSON") from exc
        except ValidationError as exc:
            raise _http_400(str(exc)) from exc

        session_ids: list[str] = []

        try:
            for payload in payloads:
                session = await run_workflow_a(
                    database,
                    payload,
                    settings=runtime_settings,
                )
                if session.id is not None:
                    session_ids.append(session.id)
        except DatabaseError as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

        return {
            "status": "accepted",
            "provider": provider.name,
            "messageCount": len(payloads),
            "sessionId": session_ids[0] if session_ids else "",
            "sessionIds": session_ids,
        }

    return router
