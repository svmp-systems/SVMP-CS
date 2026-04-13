"""Integration-style tests for the demo tenant seed script."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_seed_module():
    """Load the tenant seed script as a module for direct function testing."""

    script_path = Path(__file__).resolve().parents[3] / "scripts" / "seed_tenant.py"
    spec = importlib.util.spec_from_file_location("seed_tenant", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load tenant seed script module")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sample_tenant_seed_file_parses_into_document() -> None:
    """The sample tenant seed file should parse into the expected document shape."""

    module = _load_seed_module()
    sample_file = Path(__file__).resolve().parents[3] / "scripts" / "demo_data" / "sample_tenant.json"

    tenant_document = module.load_tenant_document(sample_file)

    assert tenant_document["tenantId"] == "Stay"
    assert tenant_document["settings"]["confidenceThreshold"] == 0.75
    assert tenant_document["domains"][0]["domainId"] == "general"
    assert tenant_document["channels"]["twilio"]["whatsappNumbers"] == ["whatsapp:+14155238886"]
    assert "premium fragrance advisor" in tenant_document["brandVoice"]


@pytest.mark.asyncio
async def test_seed_tenant_from_file_uses_writer_upsert_path(tmp_path: Path) -> None:
    """The tenant seed script should pass parsed data into the writer abstraction."""

    module = _load_seed_module()
    seed_file = tmp_path / "tenant.json"
    seed_file.write_text(
        (
            "{"
            '"tenantId": "Stay",'
            '"domains": [{"domainId": "general", "name": "General", "description": "General help"}],'
            '"channels": {"twilio": {"whatsappNumbers": ["whatsapp:+14155238886"]}},'
            '"settings": {"confidenceThreshold": 0.8},'
            '"tags": ["demo"],'
            '"brandVoice": "Warm and polished."'
            "}"
        ),
        encoding="utf-8",
    )

    class FakeWriter:
        def __init__(self) -> None:
            self.document = None

        async def upsert_tenant(self, tenant_document):
            self.document = dict(tenant_document)
            return 1

    writer = FakeWriter()

    written = await module.seed_tenant_from_file(writer, seed_file)

    assert written == 1
    assert writer.document is not None
    assert writer.document["tenantId"] == "Stay"
    assert writer.document["channels"]["twilio"]["whatsappNumbers"] == ["whatsapp:+14155238886"]
    assert writer.document["settings"]["confidenceThreshold"] == 0.8
    assert writer.document["brandVoice"] == "Warm and polished."


@pytest.mark.asyncio
async def test_mongo_tenant_writer_clears_conflicting_channel_mappings() -> None:
    """The Mongo tenant writer should remove matching channel identifiers from other tenants first."""

    module = _load_seed_module()

    class FakeCollection:
        def __init__(self) -> None:
            self.updated: list[tuple[dict, dict]] = []
            self.replaced: list[tuple[dict, dict, bool]] = []

        async def update_many(self, filter_doc: dict, update_doc: dict) -> None:
            self.updated.append((dict(filter_doc), dict(update_doc)))

        async def replace_one(self, filter_doc: dict, payload: dict, upsert: bool) -> None:
            self.replaced.append((dict(filter_doc), dict(payload), upsert))

    collection = FakeCollection()
    writer = module.MongoTenantSeedWriter(collection)

    written = await writer.upsert_tenant(
        {
            "tenantId": "Stay",
            "domains": [{"domainId": "general", "name": "General", "description": "General help"}],
            "channels": {
                "twilio": {
                    "whatsappNumbers": ["whatsapp:+14155238886"],
                    "accountSids": ["AC123"],
                }
            },
        }
    )

    assert written == 1
    assert collection.updated == [
        (
            {"tenantId": {"$ne": "Stay"}},
            {"$pull": {"channels.twilio.whatsappNumbers": {"$in": ["whatsapp:+14155238886"]}}},
        ),
        (
            {"tenantId": {"$ne": "Stay"}},
            {"$pull": {"channels.twilio.accountSids": {"$in": ["AC123"]}}},
        ),
    ]
    assert collection.replaced == [
        (
            {"tenantId": "Stay"},
            {
                "tenantId": "Stay",
                "domains": [{"domainId": "general", "name": "General", "description": "General help"}],
                "channels": {
                    "twilio": {
                        "whatsappNumbers": ["whatsapp:+14155238886"],
                        "accountSids": ["AC123"],
                    }
                },
            },
            True,
        )
    ]
