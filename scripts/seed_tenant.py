"""Seed a tenant configuration document into Supabase/Postgres."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "svmp"

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from svmp_core.config import Settings, get_settings
from svmp_core.db.supabase import SupabaseDatabase

DEFAULT_SAMPLE_FILE = REPO_ROOT / "scripts" / "demo_data" / "sample_tenant.json"


class TenantSeedSpec(BaseModel):
    """Top-level tenant seed format."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    tenant_id: str = Field(alias="tenantId")
    domains: list[dict[str, Any]]
    settings: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    channels: dict[str, Any] = Field(default_factory=dict)
    contact_info: dict[str, Any] = Field(default_factory=dict, alias="contactInfo")
    brand_voice: str | dict[str, Any] | None = Field(default=None, alias="brandVoice")

    @field_validator("tenant_id")
    @classmethod
    def _require_non_blank_tenant_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("tenantId must not be blank")
        return normalized


class TenantSeedWriter(Protocol):
    """Small write interface used by the tenant seed script and tests."""

    async def upsert_tenant(self, tenant_document: Mapping[str, Any]) -> int:
        """Upsert the provided tenant document and return the number written."""


class SupabaseTenantSeedWriter:
    """Supabase-backed writer for repeatable tenant upserts."""

    def __init__(self, database: SupabaseDatabase) -> None:
        self._database = database

    async def upsert_tenant(self, tenant_document: Mapping[str, Any]) -> int:
        await self._database.tenants.upsert_tenant(tenant_document)
        return 1


def load_tenant_document(seed_file: Path) -> dict[str, Any]:
    """Parse a tenant seed file into a tenant document."""

    raw_payload = json.loads(seed_file.read_text(encoding="utf-8"))
    tenant = TenantSeedSpec(**raw_payload)
    return tenant.model_dump(by_alias=True, exclude_none=True)


async def seed_tenant_from_file(writer: TenantSeedWriter, seed_file: Path) -> int:
    """Load a tenant seed file and write it through the provided writer."""

    tenant_document = load_tenant_document(seed_file)
    return await writer.upsert_tenant(tenant_document)


async def _run(seed_file: Path, *, settings: Settings | None = None) -> int:
    """Execute the Supabase-backed tenant seed flow and return the write count."""

    runtime_settings = settings or get_settings()
    database = SupabaseDatabase(settings=runtime_settings)
    await database.connect()
    try:
        writer = SupabaseTenantSeedWriter(database)
        return await seed_tenant_from_file(writer, seed_file)
    finally:
        await database.disconnect()


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for the tenant seed script."""

    parser = argparse.ArgumentParser(description="Seed a demo tenant document into Supabase/Postgres.")
    parser.add_argument(
        "--file",
        dest="seed_file",
        type=Path,
        default=DEFAULT_SAMPLE_FILE,
        help="Path to a JSON tenant seed file. Defaults to scripts/demo_data/sample_tenant.json.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint used for local demo tenant seeding."""

    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    written = asyncio.run(_run(args.seed_file))
    print(f"Seeded {written} tenant document from {args.seed_file}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
