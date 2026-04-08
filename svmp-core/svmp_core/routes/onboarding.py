"""Tenant onboarding routes for website-driven KB generation."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, Awaitable

from fastapi import APIRouter, HTTPException, status

from svmp_core.config import Settings, get_settings
from svmp_core.core import run_tenant_onboarding_pipeline
from svmp_core.db.base import Database
from svmp_core.exceptions import DatabaseError, ValidationError
from svmp_core.models import (
    TenantOnboardingAccepted,
    TenantOnboardingRequest,
    TenantOnboardingStatusResponse,
)


def _launch_background_task(task: Awaitable[Any]) -> asyncio.Task[Any]:
    """Schedule an async onboarding task in the current event loop."""

    return asyncio.create_task(task)


def build_onboarding_router(
    database: Database,
    *,
    settings: Settings | None = None,
) -> APIRouter:
    """Build onboarding routes bound to the provided runtime dependencies."""

    runtime_settings = settings or get_settings()
    router = APIRouter(prefix="/tenants", tags=["onboarding"])

    @router.post(
        "/onboarding",
        response_model=TenantOnboardingAccepted,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def queue_tenant_onboarding(
        request: TenantOnboardingRequest,
    ) -> TenantOnboardingAccepted:
        existing_tenant = await database.tenants.get_by_tenant_id(request.tenant_id)
        initial_tenant_document = dict(existing_tenant) if isinstance(existing_tenant, Mapping) else {}
        initial_tenant_document.update(
            {
                "tenantId": request.tenant_id,
                "tenantName": request.tenant_name,
                "websiteUrl": str(request.website_url),
                "brandVoice": request.brand_voice,
                "tags": request.tags or initial_tenant_document.get("tags", []),
                "onboarding": {
                    "status": "queued",
                    "targetFaqCount": request.target_faq_count,
                    "sourceWebsiteUrl": str(request.website_url),
                    "publicQuestionUrls": [str(url) for url in request.public_question_urls],
                },
            }
        )

        try:
            await database.tenants.upsert_tenant(initial_tenant_document)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to queue tenant onboarding",
            ) from exc

        _launch_background_task(
            run_tenant_onboarding_pipeline(
                database,
                request,
                settings=runtime_settings,
            )
        )

        return TenantOnboardingAccepted(
            tenantId=request.tenant_id,
            onboardingStatus="queued",
            websiteUrl=str(request.website_url),
        )

    @router.get(
        "/{tenant_id}/onboarding-status",
        response_model=TenantOnboardingStatusResponse,
    )
    async def get_tenant_onboarding_status(
        tenant_id: str,
    ) -> TenantOnboardingStatusResponse:
        try:
            tenant_document = await database.tenants.get_by_tenant_id(tenant_id)
        except DatabaseError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc

        if not isinstance(tenant_document, Mapping):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="tenant not found",
            )

        onboarding = tenant_document.get("onboarding", {})
        return TenantOnboardingStatusResponse(
            tenantId=str(tenant_document.get("tenantId", tenant_id)),
            websiteUrl=tenant_document.get("websiteUrl"),
            brandVoice=tenant_document.get("brandVoice"),
            onboarding=dict(onboarding) if isinstance(onboarding, Mapping) else {},
            updatedAt=tenant_document.get("updatedAt") or tenant_document.get("createdAt"),
        )

    return router
