"""Webhook routes for verification and inbound message intake."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status

from svmp_core.config import Settings, get_settings
from svmp_core.db.base import Database
from svmp_core.exceptions import DatabaseError, ValidationError
from svmp_core.models import WebhookPayload
from svmp_core.workflows import run_workflow_a


def build_webhook_router(
    database: Database,
    *,
    settings: Settings | None = None,
) -> APIRouter:
    """Build a webhook router bound to the provided runtime dependencies."""

    runtime_settings = settings or get_settings()
    router = APIRouter()

    @router.get("/webhook")
    async def verify_webhook(
        hub_mode: str | None = Query(default=None, alias="hub.mode"),
        hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
        hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
    ) -> Response:
        verify_token = runtime_settings.WHATSAPP_VERIFY_TOKEN
        expected_token = verify_token.get_secret_value() if verify_token is not None else None

        if hub_mode != "subscribe" or expected_token is None or hub_verify_token != expected_token:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="webhook verification failed")

        if hub_challenge is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing hub.challenge")

        return Response(content=hub_challenge, media_type="text/plain")

    @router.post("/webhook")
    async def intake_webhook(payload: WebhookPayload) -> dict[str, str]:
        try:
            session = await run_workflow_a(
                database,
                payload,
                settings=runtime_settings,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except DatabaseError as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

        return {
            "status": "accepted",
            "sessionId": session.id or "",
        }

    return router
