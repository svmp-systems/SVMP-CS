"""Seed a tenant configuration document into MongoDB for live demo verification."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "svmp-core"

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from motor.motor_asyncio import AsyncIOMotorClient

from svmp_core.config import Settings, get_settings

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
        """Trim and reject blank tenant IDs."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("tenantId must not be blank")
        return normalized


class TenantSeedWriter(Protocol):
    """Small write interface used by the tenant seed script and tests."""

    async def upsert_tenant(self, tenant_document: Mapping[str, Any]) -> int:
        """Upsert the provided tenant document and return the number written."""


class MongoTenantSeedWriter:
    """Mongo-backed writer for repeatable tenant upserts."""

    def __init__(self, collection) -> None:
        self._collection = collection

    @staticmethod
    def _channel_values(tenant_document: Mapping[str, Any]) -> list[tuple[str, list[str]]]:
        """Extract provider channel identifiers so conflicting mappings can be cleared."""

        channels = tenant_document.get("channels", {})
        if not isinstance(channels, Mapping):
            return []

        field_map = {
            "meta": {
                "phoneNumberIds": "channels.meta.phoneNumberIds",
                "displayNumbers": "channels.meta.displayNumbers",
            },
            "twilio": {
                "whatsappNumbers": "channels.twilio.whatsappNumbers",
                "accountSids": "channels.twilio.accountSids",
            },
        }

        extracted: list[tuple[str, list[str]]] = []
        for provider_name, provider_fields in field_map.items():
            provider_payload = channels.get(provider_name)
            if not isinstance(provider_payload, Mapping):
                continue

            for key, field_path in provider_fields.items():
                raw_values = provider_payload.get(key)
                if not isinstance(raw_values, Sequence) or isinstance(raw_values, (str, bytes)):
                    continue

                normalized_values = [
                    value.strip()
                    for value in raw_values
                    if isinstance(value, str) and value.strip()
                ]
                if normalized_values:
                    extracted.append((field_path, normalized_values))

        return extracted

    async def upsert_tenant(self, tenant_document: Mapping[str, Any]) -> int:
        """Upsert a tenant document using tenantId as the stable key."""

        payload = deepcopy(dict(tenant_document))
        tenant_id = payload["tenantId"]

        for field_path, values in self._channel_values(payload):
            await self._collection.update_many(
                {"tenantId": {"$ne": tenant_id}},
                {"$pull": {field_path: {"$in": values}}},
            )

        await self._collection.replace_one(
            {"tenantId": tenant_id},
            payload,
            upsert=True,
        )
        return 1


def load_tenant_document(seed_file: Path) -> dict[str, Any]:
    """Parse a tenant seed file into a Mongo-ready document."""

    raw_payload = json.loads(seed_file.read_text(encoding="utf-8"))
    tenant = TenantSeedSpec(**raw_payload)

    return tenant.model_dump(by_alias=True, exclude_none=True)


async def seed_tenant_from_file(writer: TenantSeedWriter, seed_file: Path) -> int:
    """Load a tenant seed file and write it through the provided writer."""

    tenant_document = load_tenant_document(seed_file)
    return await writer.upsert_tenant(tenant_document)


async def _run(seed_file: Path, *, settings: Settings | None = None) -> int:
    """Execute the Mongo-backed tenant seed flow and return the write count."""

    runtime_settings = settings or get_settings()
    client = AsyncIOMotorClient(runtime_settings.MONGODB_URI)

    try:
        collection = client[runtime_settings.MONGODB_DB_NAME][runtime_settings.MONGODB_TENANTS_COLLECTION]
        writer = MongoTenantSeedWriter(collection)
        return await seed_tenant_from_file(writer, seed_file)
    finally:
        client.close()


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for the tenant seed script."""

    parser = argparse.ArgumentParser(description="Seed a demo tenant document into MongoDB.")
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
