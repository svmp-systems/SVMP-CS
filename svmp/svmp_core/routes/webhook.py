"""Webhook routes for verification and provider-agnostic inbound intake."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status

from svmp_core.config import Settings, get_settings
from svmp_core.db.base import Database
from svmp_core.exceptions import DatabaseError, SecurityError, ValidationError
from svmp_core.integrations import get_whatsapp_provider
from svmp_core.integrations.webhook_security import verify_inbound_webhook
from svmp_core.logger import get_logger
from svmp_core.models import SessionState
from svmp_core.workflows import run_workflow_a, run_workflow_b

logger = get_logger(__name__)


def build_webhook_router(
    database: Database,
    *,
    settings: Settings | None = None,
) -> APIRouter:
    """Build a webhook router bound to the provided runtime dependencies."""

    runtime_settings = settings or get_settings()
    router = APIRouter()

    async def _attempt_inline_processing(sessions: list[SessionState]) -> None:
        unique_sessions = {
            session.id: session
            for session in sessions
            if session.id is not None
        }
        if not unique_sessions:
            return

        latest_debounce_expires_at = max(
            session.debounce_expires_at
            for session in unique_sessions.values()
        )
        delay_seconds = (
            latest_debounce_expires_at - datetime.now(timezone.utc)
        ).total_seconds()
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

        for session_id in unique_sessions:
            try:
                await run_workflow_b(
                    database,
                    settings=runtime_settings,
                    session_id=session_id,
                )
            except Exception as exc:
                logger.warning(
                    "webhook_inline_processing_failed",
                    sessionId=session_id,
                    error=str(exc),
                )

    def _http_400(detail: str) -> HTTPException:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    def _http_403(detail: str) -> HTTPException:
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    def _non_blank(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

    def _extract_provider_identities(
        provider_name: str,
        payload: Mapping[str, Any],
    ) -> list[str]:
        identities: list[str] = []

        if provider_name == "twilio":
            for key in ("To", "AccountSid"):
                value = _non_blank(payload.get(key))
                if value is not None:
                    identities.append(value)
            return identities

        if provider_name == "meta":
            raw_entries = payload.get("entry", [])
            if not isinstance(raw_entries, list):
                return identities

            for entry in raw_entries:
                if not isinstance(entry, Mapping):
                    continue
                changes = entry.get("changes", [])
                if not isinstance(changes, list):
                    continue
                for change in changes:
                    if not isinstance(change, Mapping):
                        continue
                    value = change.get("value", {})
                    if not isinstance(value, Mapping):
                        continue
                    metadata = value.get("metadata", {})
                    if not isinstance(metadata, Mapping):
                        continue
                    for key in ("phone_number_id", "display_phone_number"):
                        candidate = _non_blank(metadata.get(key))
                        if candidate is not None:
                            identities.append(candidate)

        return identities

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
    ) -> dict[str, str]:
        content_type = request.headers.get("content-type")
        resolved_tenant_id = tenant_id_header or tenant_id_query
        requested_provider = provider_header or provider_query

        try:
            raw_body = await request.body()
            if content_type is not None and "application/x-www-form-urlencoded" in content_type.lower():
                raw_payload = dict(parse_qsl(raw_body.decode("utf-8"), keep_blank_values=True))
            else:
                raw_payload = json.loads(raw_body)
                if not isinstance(raw_payload, Mapping):
                    raise ValidationError("webhook payload must be a JSON object")

            provider = get_whatsapp_provider(
                settings=runtime_settings,
                requested_provider=requested_provider,
                payload=raw_payload if isinstance(raw_payload, Mapping) else None,
                content_type=content_type,
            )

            verify_inbound_webhook(
                provider_name=provider.name,
                request_url=str(request.url),
                headers=request.headers,
                raw_body=raw_body,
                form_payload=raw_payload if isinstance(raw_payload, Mapping) else None,
                settings=runtime_settings,
            )

            if resolved_tenant_id is None and provider.name != "normalized":
                identities = _extract_provider_identities(provider.name, raw_payload)
                resolved_tenant_id = await database.tenants.resolve_tenant_id_for_provider(
                    provider=provider.name,
                    identities=identities,
                )
                if resolved_tenant_id is None:
                    raise ValidationError("tenantId could not be resolved from provider payload")

            if content_type is not None and "application/x-www-form-urlencoded" in content_type.lower():
                payloads = provider.normalize_form_payload(
                    raw_payload,
                    tenant_id=resolved_tenant_id,
                )
            else:
                payloads = provider.normalize_json_payload(
                    raw_payload,
                    tenant_id=resolved_tenant_id,
                )
        except JSONDecodeError as exc:
            raise _http_400("webhook payload must be valid JSON") from exc
        except SecurityError as exc:
            raise _http_403(str(exc)) from exc
        except ValidationError as exc:
            raise _http_400(str(exc)) from exc

        session_id = ""
        ingested_sessions: list[SessionState] = []

        try:
            for payload in payloads:
                session = await run_workflow_a(
                    database,
                    payload,
                    settings=runtime_settings,
                )
                ingested_sessions.append(session)
                if session.id is not None and not session_id:
                    session_id = session.id
            await _attempt_inline_processing(ingested_sessions)
        except ValidationError as exc:
            raise _http_400(str(exc)) from exc
        except DatabaseError as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

        return {
            "status": "accepted",
            "sessionId": session_id,
        }

    return router
