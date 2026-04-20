"""Seed dashboard tenant access for an authenticated portal user."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "svmp"

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from motor.motor_asyncio import AsyncIOMotorClient

from svmp_core.config import Settings, get_settings

ALLOWED_ROLES = {"owner", "admin", "analyst", "viewer"}
ACTIVE_STATUSES = {"trialing", "active"}


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Map one authenticated user to an SVMP tenant for dashboard access.")
    parser.add_argument("--tenant-id", required=True, help="SVMP tenantId, for example stay.")
    parser.add_argument("--auth-provider", default="clerk", help="Login provider, for example clerk.")
    parser.add_argument("--provider-user-id", default=None, help="Auth provider user id, for example Clerk user_...")
    parser.add_argument("--clerk-user-id", dest="provider_user_id", help="Alias for --provider-user-id.")
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
    client = AsyncIOMotorClient(runtime_settings.MONGODB_URI)

    try:
        database = client[runtime_settings.MONGODB_DB_NAME]
        verified_users = database[runtime_settings.MONGODB_VERIFIED_USERS_COLLECTION]
        tenants = database[runtime_settings.MONGODB_TENANTS_COLLECTION]
        billing = database[runtime_settings.MONGODB_BILLING_SUBSCRIPTIONS_COLLECTION]

        provider_user_id = args.provider_user_id.strip() if args.provider_user_id else None
        status = args.status or ("active" if provider_user_id else "invited")
        membership_payload = {
            "tenantId": args.tenant_id,
            "authProvider": args.auth_provider.strip().lower(),
            "providerUserId": provider_user_id,
            "email": args.email.strip().lower(),
            "role": args.role,
            "permissions": _permissions_for_role(args.role),
            "status": status,
            "updatedAt": now,
        }
        query = (
            {"authProvider": membership_payload["authProvider"], "providerUserId": provider_user_id}
            if provider_user_id
            else {"email": membership_payload["email"], "tenantId": args.tenant_id}
        )
        await verified_users.update_one(
            query,
            {"$set": membership_payload, "$setOnInsert": {"createdAt": now}},
            upsert=True,
        )

        if args.subscription_status:
            await billing.update_one(
                {"tenantId": args.tenant_id},
                {
                    "$set": {
                        "tenantId": args.tenant_id,
                        "status": args.subscription_status,
                        "updatedAt": now,
                    },
                    "$setOnInsert": {"createdAt": now},
                },
                upsert=True,
            )
            await tenants.update_one(
                {"tenantId": args.tenant_id},
                {
                    "$set": {
                        "billing.status": args.subscription_status,
                    },
                },
            )

        return {
            "tenantId": args.tenant_id,
            "authProvider": membership_payload["authProvider"],
            "providerUserId": provider_user_id or "",
            "role": args.role,
            "status": status,
            "subscriptionStatus": args.subscription_status or "unchanged",
        }
    finally:
        client.close()


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
