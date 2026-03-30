"""Seed tenant-scoped demo knowledge-base entries into MongoDB."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "svmp-core"

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from motor.motor_asyncio import AsyncIOMotorClient

from svmp_core.config import Settings, get_settings
from svmp_core.models import KnowledgeEntry

DEFAULT_SAMPLE_FILE = REPO_ROOT / "scripts" / "demo_data" / "sample_kb.json"


class SeedEntrySpec(BaseModel):
    """Raw entry shape accepted from a seed JSON file."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str | None = Field(default=None, alias="_id")
    domain_id: str = Field(alias="domainId")
    question: str
    answer: str
    tags: list[str] = Field(default_factory=list)
    active: bool = True

    @field_validator("id")
    @classmethod
    def _normalize_optional_id(cls, value: str | None) -> str | None:
        """Normalize optional identifiers so blank IDs do not become upsert keys."""

        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("domain_id", "question", "answer")
    @classmethod
    def _require_non_blank(cls, value: str) -> str:
        """Trim and reject blank required text fields."""

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
        """Trim and reject blank tenant IDs."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("tenantId must not be blank")
        return normalized


class KnowledgeSeedWriter(Protocol):
    """Small write interface used by the seed script and its tests."""

    async def upsert_entries(self, entries: Sequence[KnowledgeEntry]) -> int:
        """Upsert the provided entries and return the number written."""


class MongoKnowledgeSeedWriter:
    """Mongo-backed writer that performs repeatable knowledge-entry upserts."""

    def __init__(self, collection) -> None:
        self._collection = collection

    async def upsert_entries(self, entries: Sequence[KnowledgeEntry]) -> int:
        """Replace or insert knowledge entries using stable keys."""

        written = 0
        seeded_domains = {
            (entry.tenant_id, entry.domain_id)
            for entry in entries
        }

        # Reset each seeded tenant/domain slice so legacy demo documents do not
        # survive alongside the current sample corpus.
        for tenant_id, domain_id in seeded_domains:
            await self._collection.delete_many(
                {
                    "tenantId": tenant_id,
                    "domainId": domain_id,
                }
            )

        for entry in entries:
            payload = entry.model_dump(by_alias=True, exclude_none=True)
            filter_doc = (
                {"_id": entry.id}
                if entry.id
                else {
                    "tenantId": entry.tenant_id,
                    "domainId": entry.domain_id,
                    "question": entry.question,
                }
            )

            await self._collection.replace_one(filter_doc, payload, upsert=True)
            written += 1

        return written


def load_seed_entries(seed_file: Path) -> list[KnowledgeEntry]:
    """Parse a seed file and transform it into typed knowledge entries."""

    raw_payload = json.loads(seed_file.read_text(encoding="utf-8"))
    batch = SeedBatch(**raw_payload)

    return [
        KnowledgeEntry(
            _id=entry.id,
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
    return await writer.upsert_entries(entries)


async def _run(seed_file: Path, *, settings: Settings | None = None) -> int:
    """Execute the Mongo-backed seed flow and return the write count."""

    runtime_settings = settings or get_settings()
    client = AsyncIOMotorClient(runtime_settings.MONGODB_URI)

    try:
        collection = client[runtime_settings.MONGODB_DB_NAME][runtime_settings.MONGODB_KB_COLLECTION]
        writer = MongoKnowledgeSeedWriter(collection)
        return await seed_entries_from_file(writer, seed_file)
    finally:
        client.close()


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for the seed script."""

    parser = argparse.ArgumentParser(description="Seed demo knowledge-base entries into MongoDB.")
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
