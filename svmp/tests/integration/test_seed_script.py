"""Integration-style tests for the Supabase knowledge-base seed script."""

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

    assert len(entries) == 10
    assert entries[0].tenant_id == "Stay"
    assert entries[0].domain_id == "general"
    assert entries[0].id == "faq-bottle-size"


def test_shared_seed_file_parses_into_shared_knowledge_entries() -> None:
    """The shared KB seed file should parse into shared/global knowledge entries."""

    module = _load_seed_module()
    sample_file = Path(__file__).resolve().parents[3] / "scripts" / "demo_data" / "shared_kb.json"

    entries = module.load_seed_entries(sample_file)

    assert len(entries) >= 10
    assert entries[0].tenant_id == "__shared__"
    assert entries[0].domain_id == "general"
    assert entries[0].tags[0] == "shared"


def test_seed_transform_applies_top_level_tenant_to_all_entries(tmp_path: Path) -> None:
    """Top-level tenantId should be propagated into each transformed entry."""

    module = _load_seed_module()
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(
        (
            "{"
            '"tenantId": "Stay",'
            '"entries": ['
            '{"domainId": "sales", "question": "Pricing?", "answer": "Contact sales.", "tags": ["sales"]}'
            "]}"
        ),
        encoding="utf-8",
    )

    entries = module.load_seed_entries(seed_file)

    assert len(entries) == 1
    assert entries[0].tenant_id == "Stay"
    assert entries[0].domain_id == "sales"
    assert entries[0].question == "Pricing?"
    assert entries[0].id is None


@pytest.mark.asyncio
async def test_seed_entries_from_file_uses_writer_replace_path(tmp_path: Path) -> None:
    """The seed script should pass parsed entries into the writer abstraction."""

    module = _load_seed_module()
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(
        (
            "{"
            '"tenantId": "Stay",'
            '"entries": ['
            '{"_id": "faq-1", "domainId": "general", "question": "What do you do?", "answer": "We help customers."}'
            "]}"
        ),
        encoding="utf-8",
    )

    class FakeWriter:
        def __init__(self) -> None:
            self.entries = None

        async def replace_entries(self, entries):
            self.entries = list(entries)
            return len(self.entries)

    writer = FakeWriter()

    written = await module.seed_entries_from_file(writer, seed_file)

    assert written == 1
    assert writer.entries is not None
    assert writer.entries[0].id == "faq-1"
    assert writer.entries[0].tenant_id == "Stay"


@pytest.mark.asyncio
async def test_supabase_writer_replaces_each_tenant_domain_slice() -> None:
    """The Supabase writer should replace one slice per tenant/domain pair."""

    module = _load_seed_module()

    class FakeKnowledgeRepository:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, list[str]]] = []

        async def replace_entries_for_tenant_domain(self, tenant_id, domain_id, entries):
            self.calls.append((tenant_id, domain_id, [entry.id for entry in entries]))
            return len(entries)

    class FakeDatabase:
        def __init__(self) -> None:
            self.knowledge_base = FakeKnowledgeRepository()

    database = FakeDatabase()
    writer = module.SupabaseKnowledgeSeedWriter(database)
    entries = [
        module.KnowledgeEntry(
            _id="faq-1",
            tenantId="Stay",
            domainId="general",
            question="What do you do?",
            answer="We help customers.",
        ),
        module.KnowledgeEntry(
            _id="faq-2",
            tenantId="Stay",
            domainId="general",
            question="How do you ship?",
            answer="We ship nationwide.",
        ),
        module.KnowledgeEntry(
            _id="faq-3",
            tenantId="Stay",
            domainId="returns",
            question="Do you accept returns?",
            answer="Please review the returns policy.",
        ),
    ]

    written = await writer.replace_entries(entries)

    assert written == 3
    assert database.knowledge_base.calls == [
        ("Stay", "general", ["faq-1", "faq-2"]),
        ("Stay", "returns", ["faq-3"]),
    ]
