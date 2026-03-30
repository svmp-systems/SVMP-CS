"""Run a live Workflow A -> Workflow B verification against MongoDB and OpenAI."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "svmp-core"

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from motor.motor_asyncio import AsyncIOMotorClient

from svmp_core.config import Settings, get_settings
from svmp_core.db.mongo import MongoDatabase
from svmp_core.models import WebhookPayload
from svmp_core.workflows import run_workflow_a, run_workflow_b


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for live verification."""

    parser = argparse.ArgumentParser(description="Verify the live Workflow A/B path against MongoDB and OpenAI.")
    parser.add_argument("--tenant-id", default="Niyomilan", help="Tenant id to use for the verification payload.")
    parser.add_argument("--client-id", default="whatsapp", help="Client/channel id to use for the verification payload.")
    parser.add_argument("--user-id", default="demo-user-001", help="User id to use for the verification payload.")
    parser.add_argument(
        "--text",
        default="What does Niyomilan do?",
        help="Inbound message text to send through Workflow A/B.",
    )
    return parser


async def _load_latest_governance_log(
    settings: Settings,
    *,
    tenant_id: str,
    client_id: str,
    user_id: str,
) -> dict[str, Any] | None:
    """Load the latest governance log for the provided identity."""

    client = AsyncIOMotorClient(settings.MONGODB_URI)

    try:
        collection = client[settings.MONGODB_DB_NAME][settings.MONGODB_GOVERNANCE_COLLECTION]
        return await collection.find_one(
            {
                "tenantId": tenant_id,
                "clientId": client_id,
                "userId": user_id,
            },
            sort=[("timestamp", -1)],
        )
    finally:
        client.close()


async def _run(args: argparse.Namespace, *, settings: Settings | None = None) -> int:
    """Execute a live end-to-end verification against the configured runtime."""

    runtime_settings = settings or get_settings()
    runtime_settings.validate_runtime()

    database = MongoDatabase(settings=runtime_settings)
    payload = WebhookPayload(
        tenantId=args.tenant_id,
        clientId=args.client_id,
        userId=args.user_id,
        text=args.text,
    )
    current_time = datetime.now(timezone.utc)
    process_time = current_time + timedelta(milliseconds=runtime_settings.DEBOUNCE_MS + 1)

    await database.connect()
    try:
        session = await run_workflow_a(
            database,
            payload,
            settings=runtime_settings,
            now=current_time,
        )
        result = await run_workflow_b(
            database,
            settings=runtime_settings,
            now=process_time,
        )
    finally:
        await database.disconnect()

    governance_log = await _load_latest_governance_log(
        runtime_settings,
        tenant_id=args.tenant_id,
        client_id=args.client_id,
        user_id=args.user_id,
    )

    print(
        json.dumps(
            {
                "sessionId": session.id,
                "workflowB": {
                    "processed": result.processed,
                    "decision": result.decision.value if result.decision is not None else None,
                    "domainId": result.domain_id,
                    "similarityScore": result.similarity_score,
                    "answerSupplied": result.answer_supplied,
                    "reason": result.reason,
                    "matcherUsed": result.matcher_used,
                },
                "latestGovernanceLog": governance_log,
            },
            default=str,
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for live Mongo/OpenAI verification."""

    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
