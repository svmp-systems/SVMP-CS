"""Dashboard API routes for the SVMP customer portal."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from svmp_core.auth import (
    ACTIVE_SUBSCRIPTION_STATUSES,
    CONFIG_WRITE_ROLES,
    PortalRole,
    TenantContext,
    require_active_subscription,
    require_role,
    require_tenant_context,
)
from svmp_core.db.base import Database
from svmp_core.models import KnowledgeEntry


class TenantPatch(BaseModel):
    """Allowed tenant profile fields for dashboard edits."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    tenant_name: str | None = Field(default=None, alias="tenantName", max_length=120)
    website_url: str | None = Field(default=None, alias="websiteUrl", max_length=300)
    industry: str | None = Field(default=None, max_length=120)
    support_email: str | None = Field(default=None, alias="supportEmail", max_length=254)
    settings: dict[str, Any] | None = None
    onboarding: dict[str, Any] | None = None


class BrandVoicePatch(BaseModel):
    """Allowed tenant brand voice fields."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    tone: str | None = Field(default=None, max_length=500)
    use: list[str] | None = None
    avoid: list[str] | None = None
    escalation_style: str | None = Field(default=None, alias="escalationStyle", max_length=500)
    example_replies: list[str] | None = Field(default=None, alias="exampleReplies")


class KnowledgeEntryCreate(BaseModel):
    """Payload for creating a tenant-scoped knowledge-base entry."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    domain_id: str = Field(alias="domainId", min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=4000)
    tags: list[str] = Field(default_factory=list)
    active: bool = True


class KnowledgeEntryPatch(BaseModel):
    """Payload for updating a tenant-scoped knowledge-base entry."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    domain_id: str | None = Field(default=None, alias="domainId", min_length=1, max_length=80)
    question: str | None = Field(default=None, min_length=1, max_length=1000)
    answer: str | None = Field(default=None, min_length=1, max_length=4000)
    tags: list[str] | None = None
    active: bool | None = None


class WhatsAppIntegrationPatch(BaseModel):
    """Allowed WhatsApp integration status fields."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    status: str | None = Field(default=None, max_length=80)
    health: str | None = Field(default=None, max_length=80)
    setup_warnings: list[str] | None = Field(default=None, alias="setupWarnings")
    metadata: dict[str, Any] | None = None


def _allowed_actions(context: TenantContext) -> list[str]:
    """Return user-facing action ids permitted for the current context."""

    if context.subscription_status not in ACTIVE_SUBSCRIPTION_STATUSES:
        return [
            "billing.read",
            "billing.checkout",
            "billing.portal",
        ]

    actions_by_role: dict[PortalRole, Iterable[str]] = {
        PortalRole.OWNER: [
            "billing.manage",
            "team.manage",
            "integrations.manage",
            "knowledge_base.manage",
            "brand_voice.manage",
            "settings.manage",
            "sessions.read",
            "metrics.read",
            "governance.read",
        ],
        PortalRole.ADMIN: [
            "integrations.manage",
            "knowledge_base.manage",
            "brand_voice.manage",
            "sessions.read",
            "metrics.read",
            "governance.read",
        ],
        PortalRole.ANALYST: [
            "sessions.read",
            "metrics.read",
            "governance.read",
        ],
        PortalRole.VIEWER: [
            "overview.read",
            "sessions.read",
            "metrics.read",
            "governance.read",
        ],
    }

    return list(actions_by_role[context.role])


def _database_from_request(request: Request) -> Database:
    """Return the app database dependency bound during FastAPI startup."""

    return request.app.state.database


def _model_payload(model: BaseModel) -> dict[str, Any]:
    """Serialize a Pydantic model with public API aliases."""

    return model.model_dump(by_alias=True)


def _redact_sensitive(value: Any) -> Any:
    """Remove obvious secret-bearing values from dashboard responses."""

    sensitive_fragments = (
        "secret",
        "token",
        "password",
        "credential",
        "apikey",
        "api_key",
        "auth",
    )
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).replace("-", "").lower()
            if any(fragment in normalized_key for fragment in sensitive_fragments):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


def _contains_sensitive_key(value: Any) -> bool:
    """Return whether a payload includes obvious secret-bearing keys."""

    sensitive_fragments = (
        "secret",
        "token",
        "password",
        "credential",
        "apikey",
        "api_key",
        "auth",
    )
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).replace("-", "").lower()
            if any(fragment in normalized_key for fragment in sensitive_fragments):
                return True
            if _contains_sensitive_key(item):
                return True
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _public_patch(model: BaseModel) -> dict[str, Any]:
    """Return a compact alias-key payload from a patch model."""

    return model.model_dump(by_alias=True, exclude_none=True)


def _tenant_update_payload(patch: TenantPatch) -> dict[str, Any]:
    """Filter tenant patch fields down to explicitly supported updates."""

    raw = _public_patch(patch)
    payload: dict[str, Any] = {}
    for key in ("tenantName", "websiteUrl", "industry", "supportEmail", "onboarding"):
        if key in raw:
            payload[key] = raw[key]

    settings = raw.get("settings")
    if isinstance(settings, dict):
        allowed_settings = {
            key: settings[key]
            for key in ("confidenceThreshold", "autoAnswerEnabled")
            if key in settings
        }
        for key, value in allowed_settings.items():
            payload[f"settings.{key}"] = value

    return payload


async def _write_audit_log(
    database: Database,
    context: TenantContext,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    before: Any,
    after: Any,
) -> None:
    """Write a dashboard administrative audit log."""

    await database.audit_logs.create(
        {
            "tenantId": context.tenant_id,
            "actorUserId": context.user_id,
            "actorEmail": context.email,
            "action": action,
            "resourceType": resource_type,
            "resourceId": resource_id,
            "before": _redact_sensitive(before),
            "after": _redact_sensitive(after),
            "timestamp": datetime.now(timezone.utc),
        }
    )


def _tenant_profile_payload(
    tenant: dict[str, Any],
    context: TenantContext,
) -> dict[str, Any]:
    """Build a safe tenant profile payload for the dashboard."""

    settings = tenant.get("settings") if isinstance(tenant.get("settings"), dict) else {}
    brand_voice = tenant.get("brandVoice") if isinstance(tenant.get("brandVoice"), dict) else {}
    onboarding = tenant.get("onboarding") if isinstance(tenant.get("onboarding"), dict) else {}
    contact_info = tenant.get("contactInfo") if isinstance(tenant.get("contactInfo"), dict) else {}

    return {
        "tenantId": context.tenant_id,
        "tenantName": tenant.get("tenantName") or context.tenant_name,
        "websiteUrl": tenant.get("websiteUrl"),
        "industry": tenant.get("industry"),
        "supportEmail": tenant.get("supportEmail") or contact_info.get("email"),
        "domains": tenant.get("domains", []),
        "settings": _redact_sensitive(settings),
        "brandVoice": _redact_sensitive(brand_voice),
        "onboarding": onboarding,
        "billing": {
            "status": context.subscription_status.value,
            "hasActiveSubscription": context.has_active_subscription,
        },
    }


def _setup_warnings(
    *,
    tenant: dict[str, Any],
    active_kb_count: int,
    integrations: list[dict[str, Any]],
) -> list[str]:
    """Return dashboard setup warnings from currently available data."""

    warnings: list[str] = []
    brand_voice = tenant.get("brandVoice")
    if not isinstance(brand_voice, dict) or not brand_voice:
        warnings.append("Brand voice is not configured.")
    if active_kb_count == 0:
        warnings.append("Knowledge base has no active entries.")

    has_whatsapp = any(
        integration.get("provider") == "whatsapp"
        and integration.get("status") in {"connected", "healthy"}
        for integration in integrations
    )
    channels = tenant.get("channels")
    has_channel_config = isinstance(channels, dict) and (
        "meta" in channels or "twilio" in channels
    )
    if not has_whatsapp and not has_channel_config:
        warnings.append("WhatsApp integration is not connected.")

    return warnings


async def _tenant_document(
    database: Database,
    context: TenantContext,
) -> dict[str, Any]:
    tenant = await database.tenants.get_by_tenant_id(context.tenant_id)
    return dict(tenant or {})


def build_dashboard_router() -> APIRouter:
    """Build customer portal routes."""

    router = APIRouter(prefix="/api", tags=["dashboard"])

    @router.get("/me")
    async def get_me(
        context: TenantContext = Depends(require_tenant_context),
    ) -> dict[str, object]:
        """Return the authenticated user's dashboard tenant context."""

        return {
            "userId": context.user_id,
            "email": context.email,
            "organizationId": context.organization_id,
            "tenantId": context.tenant_id,
            "tenantName": context.tenant_name,
            "role": context.role.value,
            "subscriptionStatus": context.subscription_status.value,
            "hasActiveSubscription": context.has_active_subscription,
            "allowedActions": _allowed_actions(context),
        }

    @router.get("/tenant")
    async def get_tenant(
        request: Request,
        context: TenantContext = Depends(require_tenant_context),
    ) -> dict[str, Any]:
        """Return the current tenant profile without trusting browser tenant ids."""

        database = _database_from_request(request)
        tenant = await _tenant_document(database, context)
        return _tenant_profile_payload(tenant, context)

    @router.patch("/tenant")
    async def patch_tenant(
        request: Request,
        patch: TenantPatch,
        context: TenantContext = Depends(require_role(CONFIG_WRITE_ROLES)),
    ) -> dict[str, Any]:
        """Update safe tenant profile fields."""

        database = _database_from_request(request)
        before = await _tenant_document(database, context)
        payload = _tenant_update_payload(patch)
        if not payload:
            return _tenant_profile_payload(before, context)

        after = await database.tenants.update_by_tenant_id(context.tenant_id, payload)
        if after is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="tenant not found",
            )

        await _write_audit_log(
            database,
            context,
            action="tenant.updated",
            resource_type="tenant",
            resource_id=context.tenant_id,
            before=before,
            after=after,
        )
        return _tenant_profile_payload(dict(after), context)

    @router.get("/overview")
    async def get_overview(
        request: Request,
        context: TenantContext = Depends(require_active_subscription),
    ) -> dict[str, Any]:
        """Return dashboard overview metrics for the resolved tenant."""

        database = _database_from_request(request)
        tenant = await _tenant_document(database, context)
        counts = dict(await database.governance_logs.count_by_decision(context.tenant_id))
        recent_logs = await database.governance_logs.list_by_tenant(
            context.tenant_id,
            limit=5,
        )
        active_kb_entries = await database.knowledge_base.list_by_tenant(
            context.tenant_id,
            active=True,
            limit=250,
        )
        active_sessions = await database.session_state.list_by_tenant(
            context.tenant_id,
            limit=100,
        )
        integrations = [
            dict(item)
            for item in await database.tenants.list_integration_status(context.tenant_id)
        ]

        answered = int(counts.get("answered", 0))
        escalated = int(counts.get("escalated", 0))
        resolved_total = answered + escalated
        deflection_rate = answered / resolved_total if resolved_total else 0.0

        return {
            "tenantId": context.tenant_id,
            "metrics": {
                "deflectionRate": round(deflection_rate, 4),
                "aiResolved": answered,
                "humanEscalated": escalated,
                "activeSessions": len(active_sessions),
                "activeKnowledgeEntries": len(active_kb_entries),
                "humanHoursSaved": round(answered * 3 / 60, 2),
                "safetyScore": None,
            },
            "recentActivity": [_model_payload(log) for log in recent_logs],
            "setupWarnings": _setup_warnings(
                tenant=tenant,
                active_kb_count=len(active_kb_entries),
                integrations=integrations,
            ),
            "systemHealth": {
                "status": "active",
                "subscription": context.subscription_status.value,
            },
        }

    @router.get("/metrics")
    async def get_metrics(
        request: Request,
        context: TenantContext = Depends(require_active_subscription),
    ) -> dict[str, Any]:
        """Return basic metrics for the resolved tenant."""

        database = _database_from_request(request)
        counts = dict(await database.governance_logs.count_by_decision(context.tenant_id))
        answered = int(counts.get("answered", 0))
        escalated = int(counts.get("escalated", 0))
        closed = int(counts.get("closed", 0))
        total = answered + escalated + closed

        return {
            "tenantId": context.tenant_id,
            "decisionCounts": {
                "answered": answered,
                "escalated": escalated,
                "closed": closed,
                "total": total,
            },
            "deflectionRate": round(answered / (answered + escalated), 4)
            if answered + escalated
            else 0.0,
            "humanHoursSaved": round(answered * 3 / 60, 2),
        }

    @router.get("/sessions")
    async def get_sessions(
        request: Request,
        limit: int = Query(default=50, ge=1, le=100),
        context: TenantContext = Depends(require_active_subscription),
    ) -> dict[str, Any]:
        """Return recent active sessions for the resolved tenant."""

        database = _database_from_request(request)
        sessions = await database.session_state.list_by_tenant(
            context.tenant_id,
            limit=limit,
        )
        return {
            "tenantId": context.tenant_id,
            "sessions": [
                {
                    **_model_payload(session),
                    "messageCount": len(session.messages),
                    "latestMessage": session.messages[-1].text if session.messages else None,
                }
                for session in sessions
            ],
        }

    @router.get("/knowledge-base")
    async def get_knowledge_base(
        request: Request,
        active: bool | None = Query(default=None),
        search: str | None = Query(default=None, max_length=120),
        limit: int = Query(default=100, ge=1, le=250),
        context: TenantContext = Depends(require_active_subscription),
    ) -> dict[str, Any]:
        """Return tenant-scoped knowledge-base entries."""

        database = _database_from_request(request)
        entries = await database.knowledge_base.list_by_tenant(
            context.tenant_id,
            active=active,
            search=search,
            limit=limit,
        )
        return {
            "tenantId": context.tenant_id,
            "entries": [_model_payload(entry) for entry in entries],
        }

    @router.post("/knowledge-base", status_code=status.HTTP_201_CREATED)
    async def create_knowledge_entry(
        request: Request,
        payload: KnowledgeEntryCreate,
        context: TenantContext = Depends(require_role(CONFIG_WRITE_ROLES)),
    ) -> dict[str, Any]:
        """Create a tenant-scoped knowledge-base entry."""

        database = _database_from_request(request)
        entry = KnowledgeEntry(
            tenantId=context.tenant_id,
            domainId=payload.domain_id,
            question=payload.question,
            answer=payload.answer,
            tags=payload.tags,
            active=payload.active,
        )
        created = await database.knowledge_base.create(entry)
        created_payload = _model_payload(created)
        await _write_audit_log(
            database,
            context,
            action="knowledge_base.created",
            resource_type="knowledge_base",
            resource_id=created.id or "",
            before=None,
            after=created_payload,
        )
        return created_payload

    @router.patch("/knowledge-base/{entry_id}")
    async def update_knowledge_entry(
        entry_id: str,
        request: Request,
        patch: KnowledgeEntryPatch,
        context: TenantContext = Depends(require_role(CONFIG_WRITE_ROLES)),
    ) -> dict[str, Any]:
        """Update a tenant-scoped knowledge-base entry."""

        database = _database_from_request(request)
        existing_entries = await database.knowledge_base.list_by_tenant(
            context.tenant_id,
            limit=250,
        )
        before = next((entry for entry in existing_entries if entry.id == entry_id), None)
        payload = _public_patch(patch)
        if not payload:
            if before is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="knowledge-base entry not found",
                )
            return _model_payload(before)

        updated = await database.knowledge_base.update_by_id(
            context.tenant_id,
            entry_id,
            payload,
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="knowledge-base entry not found",
            )

        updated_payload = _model_payload(updated)
        await _write_audit_log(
            database,
            context,
            action="knowledge_base.updated",
            resource_type="knowledge_base",
            resource_id=entry_id,
            before=_model_payload(before) if before is not None else None,
            after=updated_payload,
        )
        return updated_payload

    @router.delete("/knowledge-base/{entry_id}")
    async def delete_knowledge_entry(
        entry_id: str,
        request: Request,
        context: TenantContext = Depends(require_role(CONFIG_WRITE_ROLES)),
    ) -> dict[str, Any]:
        """Soft-delete a tenant-scoped knowledge-base entry."""

        database = _database_from_request(request)
        existing_entries = await database.knowledge_base.list_by_tenant(
            context.tenant_id,
            limit=250,
        )
        before = next((entry for entry in existing_entries if entry.id == entry_id), None)
        updated = await database.knowledge_base.deactivate_by_id(
            context.tenant_id,
            entry_id,
            {"updatedAt": datetime.now(timezone.utc)},
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="knowledge-base entry not found",
            )

        updated_payload = _model_payload(updated)
        await _write_audit_log(
            database,
            context,
            action="knowledge_base.deactivated",
            resource_type="knowledge_base",
            resource_id=entry_id,
            before=_model_payload(before) if before is not None else None,
            after=updated_payload,
        )
        return updated_payload

    @router.get("/brand-voice")
    async def get_brand_voice(
        request: Request,
        context: TenantContext = Depends(require_active_subscription),
    ) -> dict[str, Any]:
        """Return current tenant brand voice settings."""

        database = _database_from_request(request)
        tenant = await _tenant_document(database, context)
        brand_voice = tenant.get("brandVoice")
        return {
            "tenantId": context.tenant_id,
            "brandVoice": _redact_sensitive(brand_voice if isinstance(brand_voice, dict) else {}),
        }

    @router.patch("/brand-voice")
    async def patch_brand_voice(
        request: Request,
        patch: BrandVoicePatch,
        context: TenantContext = Depends(require_role(CONFIG_WRITE_ROLES)),
    ) -> dict[str, Any]:
        """Update tenant brand voice settings."""

        database = _database_from_request(request)
        before_tenant = await _tenant_document(database, context)
        before_brand_voice = before_tenant.get("brandVoice")
        current_brand_voice = before_brand_voice if isinstance(before_brand_voice, dict) else {}
        payload = {"brandVoice": {**current_brand_voice, **_public_patch(patch)}}
        after = await database.tenants.update_by_tenant_id(context.tenant_id, payload)
        if after is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="tenant not found",
            )

        after_brand_voice = after.get("brandVoice") if isinstance(after, dict) else {}
        await _write_audit_log(
            database,
            context,
            action="brand_voice.updated",
            resource_type="tenant",
            resource_id=context.tenant_id,
            before=before_brand_voice,
            after=after_brand_voice,
        )
        return {
            "tenantId": context.tenant_id,
            "brandVoice": _redact_sensitive(after_brand_voice),
        }

    @router.get("/governance")
    async def get_governance(
        request: Request,
        limit: int = Query(default=100, ge=1, le=250),
        context: TenantContext = Depends(require_active_subscription),
    ) -> dict[str, Any]:
        """Return tenant-scoped governance logs."""

        database = _database_from_request(request)
        logs = await database.governance_logs.list_by_tenant(
            context.tenant_id,
            limit=limit,
        )
        return {
            "tenantId": context.tenant_id,
            "logs": [_model_payload(log) for log in logs],
        }

    @router.get("/integrations")
    async def get_integrations(
        request: Request,
        context: TenantContext = Depends(require_active_subscription),
    ) -> dict[str, Any]:
        """Return tenant integration status without leaking provider secrets."""

        database = _database_from_request(request)
        integration_status = await database.tenants.list_integration_status(
            context.tenant_id,
        )
        safe_statuses = [_redact_sensitive(dict(item)) for item in integration_status]
        providers = {
            str(item.get("provider"))
            for item in safe_statuses
            if isinstance(item.get("provider"), str)
        }
        if "whatsapp" not in providers:
            safe_statuses.insert(
                0,
                {
                    "tenantId": context.tenant_id,
                    "provider": "whatsapp",
                    "status": "not_connected",
                    "health": "unknown",
                    "setupWarnings": ["WhatsApp status has not been configured."],
                },
            )

        return {
            "tenantId": context.tenant_id,
            "integrations": safe_statuses
            + [
                {"provider": "slack", "status": "coming_soon"},
                {"provider": "shopify", "status": "coming_soon"},
                {"provider": "zendesk", "status": "coming_soon"},
            ],
        }

    @router.patch("/integrations/whatsapp")
    async def patch_whatsapp_integration(
        request: Request,
        patch: WhatsAppIntegrationPatch,
        context: TenantContext = Depends(require_role(CONFIG_WRITE_ROLES)),
    ) -> dict[str, Any]:
        """Update WhatsApp integration status without accepting secrets."""

        payload = _public_patch(patch)
        if _contains_sensitive_key(payload):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="integration secrets must not be submitted to this endpoint",
            )

        database = _database_from_request(request)
        before_records = await database.tenants.list_integration_status(context.tenant_id)
        before = next(
            (record for record in before_records if record.get("provider") == "whatsapp"),
            None,
        )
        after = await database.tenants.update_integration_status(
            context.tenant_id,
            "whatsapp",
            payload,
        )
        if after is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to update WhatsApp integration status",
            )

        await _write_audit_log(
            database,
            context,
            action="integration.whatsapp.updated",
            resource_type="integration_status",
            resource_id="whatsapp",
            before=before,
            after=after,
        )
        return _redact_sensitive(dict(after))

    return router
