"""Run a live Workflow A -> Workflow B verification against Supabase/Postgres and OpenAI."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "svmp"

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from svmp_core.config import Settings, get_settings
from svmp_core.db.supabase import SupabaseDatabase
from svmp_core.models import WebhookPayload
from svmp_core.workflows import run_workflow_a, run_workflow_b


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for live verification."""

    parser = argparse.ArgumentParser(
        description="Verify the live Workflow A/B path against Supabase/Postgres and OpenAI."
    )
    parser.add_argument("--tenant-id", default="Stay", help="Tenant id to use for the verification payload.")
    parser.add_argument("--client-id", default="whatsapp", help="Client/channel id to use for the verification payload.")
    parser.add_argument("--user-id", default="demo-user-001", help="User id to use for the verification payload.")
    parser.add_argument(
        "--text",
        default="What size are STAY Parfums bottles?",
        help="Inbound message text to send through Workflow A/B.",
    )
    return parser


async def _run(args: argparse.Namespace, *, settings: Settings | None = None) -> int:
    """Execute a live end-to-end verification against the configured runtime."""

    runtime_settings = settings or get_settings()
    runtime_settings.validate_runtime()

    database = SupabaseDatabase(settings=runtime_settings)
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
        governance_logs = await database.governance_logs.list_by_tenant(args.tenant_id, limit=10)
    finally:
        await database.disconnect()

    governance_log = next(
        (
            log.model_dump(by_alias=True)
            for log in governance_logs
            if log.client_id == args.client_id and log.user_id == args.user_id
        ),
        None,
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
    """CLI entrypoint for live verification."""

    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
