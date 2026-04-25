"""Seed tenant-scoped demo knowledge-base entries into Supabase/Postgres."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "svmp"

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from svmp_core.config import Settings, get_settings
from svmp_core.db.supabase import SupabaseDatabase
from svmp_core.models import KnowledgeEntry

DEFAULT_SAMPLE_FILE = REPO_ROOT / "scripts" / "demo_data" / "sample_kb.json"


class SeedEntrySpec(BaseModel):
    """Raw entry shape accepted from a seed JSON file."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str | None = Field(default=None, validation_alias=AliasChoices("id", "_id"))
    domain_id: str = Field(alias="domainId")
    question: str
    answer: str
    tags: list[str] = Field(default_factory=list)
    active: bool = True

    @field_validator("id")
    @classmethod
    def _normalize_optional_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("domain_id", "question", "answer")
    @classmethod
    def _require_non_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("seed entry fields must not be blank")
        return normalized


class SeedBatch(BaseModel):
    """Top-level seed file format for one tenant's FAQ corpus."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    tenant_id: str = Field(alias="tenantId")
    entries: list[SeedEntrySpec]

    @field_validator("tenant_id")
    @classmethod
    def _require_non_blank_tenant(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("tenantId must not be blank")
        return normalized


class KnowledgeSeedWriter(Protocol):
    """Small write interface used by the seed script and its tests."""

    async def replace_entries(self, entries: Sequence[KnowledgeEntry]) -> int:
        """Replace the provided entries and return the number written."""


class SupabaseKnowledgeSeedWriter:
    """Supabase-backed writer that replaces seeded tenant/domain slices."""

    def __init__(self, database: SupabaseDatabase) -> None:
        self._database = database

    async def replace_entries(self, entries: Sequence[KnowledgeEntry]) -> int:
        grouped: dict[tuple[str, str], list[KnowledgeEntry]] = defaultdict(list)
        for entry in entries:
            grouped[(entry.tenant_id, entry.domain_id)].append(entry)

        written = 0
        for (tenant_id, domain_id), group in grouped.items():
            written += await self._database.knowledge_base.replace_entries_for_tenant_domain(
                tenant_id,
                domain_id,
                group,
            )
        return written


def load_seed_entries(seed_file: Path) -> list[KnowledgeEntry]:
    """Parse a seed file and transform it into typed knowledge entries."""

    raw_payload = json.loads(seed_file.read_text(encoding="utf-8"))
    batch = SeedBatch(**raw_payload)

    return [
        KnowledgeEntry(
            id=entry.id,
            tenantId=batch.tenant_id,
            domainId=entry.domain_id,
            question=entry.question,
            answer=entry.answer,
            tags=list(entry.tags),
            active=entry.active,
        )
        for entry in batch.entries
    ]


async def seed_entries_from_file(writer: KnowledgeSeedWriter, seed_file: Path) -> int:
    """Load a seed file and write its entries through the provided writer."""

    entries = load_seed_entries(seed_file)
    return await writer.replace_entries(entries)


async def _run(seed_file: Path, *, settings: Settings | None = None) -> int:
    """Execute the Supabase-backed seed flow and return the write count."""

    runtime_settings = settings or get_settings()
    database = SupabaseDatabase(settings=runtime_settings)
    await database.connect()
    try:
        writer = SupabaseKnowledgeSeedWriter(database)
        return await seed_entries_from_file(writer, seed_file)
    finally:
        await database.disconnect()


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for the seed script."""

    parser = argparse.ArgumentParser(description="Seed demo knowledge-base entries into Supabase/Postgres.")
    parser.add_argument(
        "--file",
        dest="seed_file",
        type=Path,
        default=DEFAULT_SAMPLE_FILE,
        help="Path to a JSON seed file. Defaults to scripts/demo_data/sample_kb.json.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint used for local demo seeding."""

    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    written = asyncio.run(_run(args.seed_file))
    print(f"Seeded {written} knowledge base entries from {args.seed_file}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
