"""Integration-style tests for the demo knowledge-base seed script."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_seed_module():
    """Load the seed script as a module for direct function testing."""

    script_path = Path(__file__).resolve().parents[3] / "scripts" / "seed_knowledge_base.py"
    spec = importlib.util.spec_from_file_location("seed_knowledge_base", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load seed script module")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sample_seed_file_parses_into_knowledge_entries() -> None:
    """The demo seed file should parse into typed knowledge entries."""

    module = _load_seed_module()
    sample_file = Path(__file__).resolve().parents[3] / "scripts" / "demo_data" / "sample_kb.json"

    entries = module.load_seed_entries(sample_file)

    assert len(entries) == 3
    assert entries[0].tenant_id == "Niyomilan"
    assert entries[0].domain_id == "general"
    assert entries[0].id == "faq-about-company"


def test_seed_transform_applies_top_level_tenant_to_all_entries(tmp_path: Path) -> None:
    """Top-level tenantId should be propagated into each transformed entry."""

    module = _load_seed_module()
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(
        (
            '{'
            '"tenantId": "Niyomilan",'
            '"entries": ['
            '{"domainId": "sales", "question": "Pricing?", "answer": "Contact sales.", "tags": ["sales"]}'
            "]}"
        ),
        encoding="utf-8",
    )

    entries = module.load_seed_entries(seed_file)

    assert len(entries) == 1
    assert entries[0].tenant_id == "Niyomilan"
    assert entries[0].domain_id == "sales"
    assert entries[0].question == "Pricing?"
    assert entries[0].id is None


@pytest.mark.asyncio
async def test_seed_entries_from_file_uses_writer_upsert_path(tmp_path: Path) -> None:
    """The seed script should pass parsed entries into the writer abstraction."""

    module = _load_seed_module()
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(
        (
            '{'
            '"tenantId": "Niyomilan",'
            '"entries": ['
            '{"_id": "faq-1", "domainId": "general", "question": "What do you do?", "answer": "We help customers."}'
            "]}"
        ),
        encoding="utf-8",
    )

    class FakeWriter:
        def __init__(self) -> None:
            self.entries = None

        async def upsert_entries(self, entries):
            self.entries = list(entries)
            return len(self.entries)

    writer = FakeWriter()

    written = await module.seed_entries_from_file(writer, seed_file)

    assert written == 1
    assert writer.entries is not None
    assert writer.entries[0].id == "faq-1"
    assert writer.entries[0].tenant_id == "Niyomilan"


@pytest.mark.asyncio
async def test_mongo_writer_clears_seeded_domain_before_reinserting() -> None:
    """The Mongo writer should replace a tenant/domain slice, not append to it."""

    module = _load_seed_module()

    class FakeCollection:
        def __init__(self) -> None:
            self.deleted_filters: list[dict] = []
            self.replaced: list[tuple[dict, dict, bool]] = []

        async def delete_many(self, query: dict) -> None:
            self.deleted_filters.append(dict(query))

        async def replace_one(self, filter_doc: dict, payload: dict, upsert: bool) -> None:
            self.replaced.append((dict(filter_doc), dict(payload), upsert))

    collection = FakeCollection()
    writer = module.MongoKnowledgeSeedWriter(collection)
    entries = [
        module.KnowledgeEntry(
            _id="faq-1",
            tenantId="Niyomilan",
            domainId="general",
            question="What do you do?",
            answer="We help customers.",
        ),
        module.KnowledgeEntry(
            _id="faq-2",
            tenantId="Niyomilan",
            domainId="general",
            question="How does support work?",
            answer="We automate tier-1 support.",
        ),
    ]

    written = await writer.upsert_entries(entries)

    assert written == 2
    assert collection.deleted_filters == [{"tenantId": "Niyomilan", "domainId": "general"}]
    assert len(collection.replaced) == 2
