"""Seed dashboard tenant access for a Supabase-authenticated portal user."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "svmp"

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from sqlalchemy import text

from svmp_core.config import Settings, get_settings
from svmp_core.db.supabase import SupabaseDatabase

ALLOWED_ROLES = {"owner", "admin", "analyst", "viewer"}
ACTIVE_STATUSES = {"trialing", "active"}


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Map one authenticated user to an SVMP tenant for dashboard access."
    )
    parser.add_argument("--tenant-id", required=True, help="SVMP tenantId, for example stay.")
    parser.add_argument("--auth-provider", default="supabase", help="Login provider, for example supabase.")
    parser.add_argument("--provider-user-id", default=None, help="Auth provider user id, for example a Supabase auth UUID.")
    parser.add_argument("--supabase-user-id", dest="provider_user_id", help="Alias for --provider-user-id.")
    parser.add_argument("--email", required=True, help="User email for audit/display context.")
    parser.add_argument("--role", default="owner", choices=sorted(ALLOWED_ROLES), help="Dashboard role.")
    parser.add_argument(
        "--status",
        choices=["active", "invited", "suspended", "removed"],
        default=None,
        help="Access status. Defaults to active when provider user id is present, otherwise invited.",
    )
    parser.add_argument(
        "--subscription-status",
        default=None,
        help="Optional billing status to upsert, for example active or trialing.",
    )
    return parser


async def seed_portal_access(args: argparse.Namespace, *, settings: Settings | None = None) -> dict[str, str]:
    runtime_settings = settings or get_settings()
    now = datetime.now(timezone.utc)
    database = SupabaseDatabase(settings=runtime_settings)
    await database.connect()

    try:
        await database.tenants.upsert_tenant({"tenantId": args.tenant_id})

        provider_user_id = args.provider_user_id.strip() if args.provider_user_id else None
        status = args.status or ("active" if provider_user_id else "invited")
        membership_payload = {
            "tenant_id": args.tenant_id,
            "auth_provider": args.auth_provider.strip().lower(),
            "provider_user_id": provider_user_id,
            "email": args.email.strip().lower(),
            "role": args.role,
            "permissions": json.dumps(_permissions_for_role(args.role), ensure_ascii=True),
            "status": status,
            "invited_at": now if status == "invited" else None,
            "accepted_at": now if status == "active" else None,
            "created_at": now,
            "updated_at": now,
        }

        async with database._engine.begin() as connection:  # type: ignore[union-attr]
            if provider_user_id:
                existing = await connection.execute(
                    text(
                        """
                        SELECT id
                        FROM tenant_memberships
                        WHERE auth_provider = :auth_provider
                          AND provider_user_id = :provider_user_id
                        LIMIT 1
                        """
                    ),
                    {
                        "auth_provider": membership_payload["auth_provider"],
                        "provider_user_id": provider_user_id,
                    },
                )
            else:
                existing = await connection.execute(
                    text(
                        """
                        SELECT id
                        FROM tenant_memberships
                        WHERE tenant_id = :tenant_id
                          AND lower(email) = :email
                        LIMIT 1
                        """
                    ),
                    {
                        "tenant_id": args.tenant_id,
                        "email": args.email.strip().lower(),
                    },
                )

            existing_row = existing.first()
            if existing_row is not None:
                await connection.execute(
                    text(
                        """
                        UPDATE tenant_memberships
                        SET
                            tenant_id = :tenant_id,
                            auth_provider = :auth_provider,
                            provider_user_id = :provider_user_id,
                            email = :email,
                            organization_id = :organization_id,
                            role = :role,
                            permissions = CAST(:permissions AS jsonb),
                            status = :status,
                            invited_at = :invited_at,
                            accepted_at = :accepted_at,
                            updated_at = :updated_at
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": existing_row._mapping["id"],
                        "organization_id": args.tenant_id,
                        **membership_payload,
                    },
                )
            else:
                await connection.execute(
                    text(
                        """
                        INSERT INTO tenant_memberships (
                            id,
                            tenant_id,
                            auth_provider,
                            provider_user_id,
                            email,
                            organization_id,
                            role,
                            permissions,
                            status,
                            invited_at,
                            accepted_at,
                            created_at,
                            updated_at
                        ) VALUES (
                            :id,
                            :tenant_id,
                            :auth_provider,
                            :provider_user_id,
                            :email,
                            :organization_id,
                            :role,
                            CAST(:permissions AS jsonb),
                            :status,
                            :invited_at,
                            :accepted_at,
                            :created_at,
                            :updated_at
                        )
                        """
                    ),
                    {
                        "id": provider_user_id or f"invite-{args.tenant_id}-{args.email.strip().lower()}",
                        "organization_id": args.tenant_id,
                        **membership_payload,
                    },
                )

        if args.subscription_status:
            await database.billing_subscriptions.upsert_by_tenant_id(
                args.tenant_id,
                {
                    "status": args.subscription_status,
                    "updatedAt": now,
                },
            )
            await database.tenants.update_by_tenant_id(
                args.tenant_id,
                {"billing.status": args.subscription_status},
            )

        return {
            "tenantId": args.tenant_id,
            "authProvider": membership_payload["auth_provider"],
            "providerUserId": provider_user_id or "",
            "role": args.role,
            "status": status,
            "subscriptionStatus": args.subscription_status or "unchanged",
        }
    finally:
        await database.disconnect()


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    if args.subscription_status and args.subscription_status not in ACTIVE_STATUSES:
        parser.error("--subscription-status should be active or trialing when seeding access manually")

    result = asyncio.run(seed_portal_access(args))
    print(
        "Seeded portal access: "
        f"tenant={result['tenantId']} "
        f"provider={result['authProvider']} "
        f"user={result['providerUserId'] or 'pending-email-invite'} "
        f"role={result['role']} "
        f"status={result['status']} "
        f"subscription={result['subscriptionStatus']}"
    )
    return 0


def _permissions_for_role(role: str) -> list[str]:
    permissions_by_role = {
        "owner": ["read", "write", "admin", "team.manage", "billing.manage"],
        "admin": ["read", "write", "team.manage"],
        "analyst": ["read"],
        "viewer": ["read"],
    }
    return permissions_by_role.get(role, ["read"])


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
