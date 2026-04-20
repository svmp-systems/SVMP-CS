"""Integration-style tests for the Mongo database adapter."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from svmp_core.config import Settings
from svmp_core.db.mongo import MongoDatabase
from svmp_core.models import GovernanceDecision, GovernanceLog, MessageItem, SessionState


class FakeInsertResult:
    """Minimal insert result shape used by the fake collection."""

    def __init__(self, inserted_id: str) -> None:
        self.inserted_id = inserted_id


class FakeInsertManyResult:
    """Minimal insert-many result shape used by the fake collection."""

    def __init__(self, inserted_ids: list[str]) -> None:
        self.inserted_ids = inserted_ids


class FakeDeleteResult:
    """Minimal delete result shape used by the fake collection."""

    def __init__(self, deleted_count: int) -> None:
        self.deleted_count = deleted_count


class FakeCursor:
    """Async cursor wrapper for list queries."""

    def __init__(self, documents: list[dict]) -> None:
        self._documents = documents

    async def to_list(self, length=None) -> list[dict]:
        return deepcopy(self._documents)


class FakeCollection:
    """Very small in-memory collection with the methods the adapter uses."""

    def __init__(self) -> None:
        self.documents: list[dict] = []
        self.indexes: list[dict] = []
        self._counter = 0

    async def create_index(self, keys, **kwargs):
        self.indexes.append({"keys": list(keys), "kwargs": kwargs})
        return kwargs.get("name", f"index_{len(self.indexes)}")

    async def insert_one(self, document: dict) -> FakeInsertResult:
        stored = deepcopy(document)
        self._counter += 1
        stored.setdefault("_id", f"id-{self._counter}")
        self.documents.append(stored)
        return FakeInsertResult(stored["_id"])

    async def insert_many(self, documents: list[dict]) -> FakeInsertManyResult:
        inserted_ids: list[str] = []
        for document in documents:
            result = await self.insert_one(document)
            inserted_ids.append(result.inserted_id)
        return FakeInsertManyResult(inserted_ids)

    async def find_one(self, query: dict) -> dict | None:
        for document in self.documents:
            if _matches(document, query):
                return deepcopy(document)
        return None

    async def find_one_and_update(self, query: dict, update: dict, return_document=None, sort=None):
        candidates = [document for document in self.documents if _matches(document, query)]
        if not candidates:
            return None

        if sort:
            for key, direction in reversed(sort):
                reverse = direction == -1
                candidates.sort(key=lambda item: item.get(key), reverse=reverse)

        target = candidates[0]
        for key, value in update.get("$set", {}).items():
            target[key] = deepcopy(value)
        return deepcopy(target)

    def find(self, query: dict) -> FakeCursor:
        matches = [document for document in self.documents if _matches(document, query)]
        return FakeCursor(matches)

    async def delete_many(self, query: dict) -> FakeDeleteResult:
        original_count = len(self.documents)
        self.documents = [document for document in self.documents if not _matches(document, query)]
        return FakeDeleteResult(original_count - len(self.documents))


class FakeDatabaseHandle:
    """Mapping-style fake database that returns named collections."""

    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]


class FakeMotorClient:
    """Tiny fake motor client for connect/disconnect tests."""

    def __init__(self) -> None:
        self.databases: dict[str, FakeDatabaseHandle] = {}
        self.closed = False

    def __getitem__(self, name: str) -> FakeDatabaseHandle:
        if name not in self.databases:
            self.databases[name] = FakeDatabaseHandle()
        return self.databases[name]

    def close(self) -> None:
        self.closed = True


def _matches(document: dict, query: dict) -> bool:
    """Evaluate the small subset of Mongo filters used by the adapter."""

    if "$or" in query:
        clauses = query.get("$or", [])
        if not any(_matches(document, clause) for clause in clauses):
            return False

    for key, expected in query.items():
        if key == "$or":
            continue
        actual = _lookup(document, key)
        if isinstance(expected, dict):
            for operator, operand in expected.items():
                if operator == "$lte" and not (actual <= operand):
                    return False
                if operator == "$lt" and not (actual < operand):
                    return False
                if operator == "$ne" and not (actual != operand):
                    return False
                if operator == "$exists" and ((actual is not None) is not bool(operand)):
                    return False
                if operator == "$in" and actual not in operand:
                    return False
        elif isinstance(actual, list):
            if expected not in actual:
                return False
        elif actual != expected:
            return False
    return True


def _lookup(document: dict, dotted_key: str):
    """Return a nested document value using dotted-key Mongo semantics."""

    current = document
    for part in dotted_key.split("."):
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return None
            current = current[index]
            continue
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _build_settings() -> Settings:
    """Create deterministic settings for database tests."""

    return Settings(
        _env_file=None,
        MONGODB_URI="mongodb://unit-test",
        MONGODB_DB_NAME="svmp_test",
        MONGODB_SESSION_COLLECTION="session_state",
        MONGODB_KB_COLLECTION="knowledge_base",
        MONGODB_GOVERNANCE_COLLECTION="governance_logs",
        MONGODB_TENANTS_COLLECTION="tenants",
    )


@pytest.mark.asyncio
async def test_connect_initializes_repositories_and_indexes(monkeypatch: pytest.MonkeyPatch) -> None:
    """MongoDatabase should wire repositories and create expected indexes."""

    fake_client = FakeMotorClient()
    captured: dict[str, str] = {}

    def fake_client_factory(uri: str) -> FakeMotorClient:
        captured["uri"] = uri
        return fake_client

    monkeypatch.setattr("svmp_core.db.mongo.AsyncIOMotorClient", fake_client_factory)

    database = MongoDatabase(settings=_build_settings())

    await database.connect()

    assert captured["uri"] == "mongodb://unit-test"
    assert database.session_state is not None
    assert database.knowledge_base is not None
    assert database.governance_logs is not None
    assert database.tenants is not None

    fake_db = fake_client["svmp_test"]
    assert len(fake_db["session_state"].indexes) == 2
    assert len(fake_db["knowledge_base"].indexes) == 1
    assert len(fake_db["governance_logs"].indexes) == 1
    assert len(fake_db["tenants"].indexes) == 1
    assert len(fake_db["verified_users"].indexes) == 3
    assert len(fake_db["billing_subscriptions"].indexes) == 3
    assert len(fake_db["integration_status"].indexes) == 1
    assert len(fake_db["audit_logs"].indexes) == 3
    assert len(fake_db["provider_events"].indexes) == 2
    assert fake_db["tenants"].indexes[0]["kwargs"] == {
        "unique": True,
        "name": "tenant_id_unique",
        "partialFilterExpression": {
            "tenantId": {
                "$exists": True,
                "$type": "string",
            }
        },
    }
    assert fake_db["verified_users"].indexes[0]["kwargs"]["name"] == "verified_user_provider_unique"
    assert fake_db["verified_users"].indexes[0]["kwargs"]["unique"] is True

    await database.disconnect()

    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_session_repository_round_trip_and_ready_acquisition() -> None:
    """Session repository should create, fetch, update, and acquire ready sessions."""

    fake_client = FakeMotorClient()
    database = MongoDatabase(settings=_build_settings(), client=fake_client)
    await database.connect()

    now = datetime.now(timezone.utc)
    created = await database.session_state.create(
        SessionState(
            tenant_id="Niyomilan",
            client_id="whatsapp",
            user_id="9845891194",
            messages=[MessageItem(text="hello")],
            debounce_expires_at=now - timedelta(seconds=1),
        )
    )

    fetched = await database.session_state.get_by_identity("Niyomilan", "whatsapp", "9845891194")
    assert fetched is not None
    assert fetched.id == created.id

    fetched_by_id = await database.session_state.get_by_id("Niyomilan", created.id)
    assert fetched_by_id is not None
    assert fetched_by_id.id == created.id
    assert await database.session_state.get_by_id("OtherTenant", created.id) is None

    updated = await database.session_state.update_by_id(created.id, {"status": "closed"})
    assert updated is not None
    assert updated.status == "closed"
    fetched_closed = await database.session_state.get_by_identity("Niyomilan", "whatsapp", "9845891194")
    assert fetched_closed is not None
    assert fetched_closed.status == "closed"

    fetched_after_close = await database.session_state.get_by_identity("Niyomilan", "whatsapp", "9845891194")
    assert fetched_after_close is not None
    assert fetched_after_close.id == created.id

    reopened = await database.session_state.update_by_id(
        created.id,
        {
            "status": "open",
            "processing": False,
            "debounce_expires_at": now - timedelta(seconds=2),
        },
    )
    assert reopened is not None
    assert reopened.status == "open"

    acquired_specific = await database.session_state.acquire_ready_session_by_id(created.id, now)
    assert acquired_specific is not None
    assert acquired_specific.id == created.id
    assert acquired_specific.processing is True

    reset = await database.session_state.update_by_id(
        created.id,
        {
            "processing": False,
            "debounce_expires_at": now - timedelta(seconds=2),
        },
    )
    assert reset is not None

    acquired = await database.session_state.acquire_ready_session(now)
    assert acquired is not None
    assert acquired.id == created.id
    assert acquired.processing is True


@pytest.mark.asyncio
async def test_session_repository_recovers_stale_processing_locks() -> None:
    """Ready sessions stuck in processing should be retried after the lock timeout."""

    fake_client = FakeMotorClient()
    settings = _build_settings().model_copy(
        update={"WORKFLOW_B_PROCESSING_LOCK_TIMEOUT_SECONDS": 60}
    )
    database = MongoDatabase(settings=settings, client=fake_client)
    await database.connect()

    now = datetime.now(timezone.utc)
    stale_session = await database.session_state.create(
        SessionState(
            tenant_id="Niyomilan",
            client_id="whatsapp",
            user_id="9845891194",
            processing=True,
            messages=[MessageItem(text="retry me")],
            updated_at=now - timedelta(seconds=120),
            debounce_expires_at=now - timedelta(seconds=120),
        )
    )
    await database.session_state.create(
        SessionState(
            tenant_id="Done",
            client_id="whatsapp",
            user_id="9845000000",
            processing=True,
            messages=[],
            updated_at=now - timedelta(seconds=120),
            debounce_expires_at=now - timedelta(seconds=120),
        )
    )

    acquired = await database.session_state.acquire_ready_session(now)

    assert acquired is not None
    assert acquired.id == stale_session.id
    assert acquired.messages[0].text == "retry me"


@pytest.mark.asyncio
async def test_knowledge_governance_and_tenant_repositories() -> None:
    """Knowledge, governance, and tenant repos should expose the expected CRUD surface."""

    fake_client = FakeMotorClient()
    database = MongoDatabase(settings=_build_settings(), client=fake_client)
    await database.connect()

    fake_db = fake_client["svmp_test"]
    fake_db["knowledge_base"].documents.extend(
        [
            {
                "_id": "faq-1",
                "tenantId": "Niyomilan",
                "domainId": "general",
                "question": "What do you do?",
                "answer": "We help customers.",
                "active": True,
            },
            {
                "_id": "shared-1",
                "tenantId": "__shared__",
                "domainId": "general",
                "question": "Hi",
                "answer": "Hi! How can I help?",
                "active": True,
            },
            {
                "_id": "faq-2",
                "tenantId": "Niyomilan",
                "domainId": "general",
                "question": "Old answer?",
                "answer": "Ignore this one.",
                "active": False,
            },
        ]
    )
    fake_db["tenants"].documents.append(
        {
            "_id": "tenant-1",
            "tenantId": "Niyomilan",
            "settings": {"confidenceThreshold": 0.75},
            "brandVoice": "Warm, polished, and premium.",
            "tags": ["ecom"],
        }
    )

    entries = await database.knowledge_base.list_active_by_tenant_and_domain("Niyomilan", "general")
    assert len(entries) == 2
    assert entries[0].id == "faq-1"
    assert entries[1].id == "shared-1"

    log = await database.governance_logs.create(
        GovernanceLog(
            tenant_id="Niyomilan",
            client_id="whatsapp",
            user_id="9845891194",
            decision=GovernanceDecision.ANSWERED,
            similarity_score=0.91,
            combined_text="what do you do",
            answer_supplied="We help customers.",
        )
    )
    assert log.id is not None

    tenant = await database.tenants.get_by_tenant_id("Niyomilan")
    assert tenant is not None
    assert tenant["tenantId"] == "Niyomilan"
    assert tenant["settings"]["confidenceThreshold"] == 0.75
    assert tenant["brandVoice"] == "Warm, polished, and premium."


@pytest.mark.asyncio
async def test_tenant_repository_resolves_tenant_from_provider_channel_identities() -> None:
    """Tenant repository should resolve tenants from stored Meta and Twilio channel mappings."""

    fake_client = FakeMotorClient()
    database = MongoDatabase(settings=_build_settings(), client=fake_client)
    await database.connect()

    fake_db = fake_client["svmp_test"]
    fake_db["tenants"].documents.extend(
        [
            {
                "_id": "tenant-1",
                "tenantId": "Niyomilan",
                "channels": {
                    "meta": {
                        "phoneNumberIds": ["1234567890"],
                        "displayNumbers": ["+15551234567"],
                    },
                    "twilio": {
                        "whatsappNumbers": ["whatsapp:+14155238886"],
                        "accountSids": ["AC123"],
                    },
                },
            }
        ]
    )

    meta_tenant = await database.tenants.resolve_tenant_id_for_provider(
        provider="meta",
        identities=["1234567890"],
    )
    twilio_tenant = await database.tenants.resolve_tenant_id_for_provider(
        provider="twilio",
        identities=["whatsapp:+14155238886", "AC123"],
    )
    missing_tenant = await database.tenants.resolve_tenant_id_for_provider(
        provider="twilio",
        identities=["whatsapp:+19999999999"],
    )

    assert meta_tenant == "Niyomilan"
    assert twilio_tenant == "Niyomilan"
    assert missing_tenant is None


@pytest.mark.asyncio
async def test_delete_stale_sessions_returns_deleted_count() -> None:
    """Deleting stale sessions should report the number of removed documents."""

    fake_client = FakeMotorClient()
    database = MongoDatabase(settings=_build_settings(), client=fake_client)
    await database.connect()

    fake_db = fake_client["svmp_test"]
    fake_db["session_state"].documents.extend(
        [
            {
                "_id": "old",
                "tenantId": "Niyomilan",
                "clientId": "whatsapp",
                "userId": "1",
                "status": "open",
                "processing": False,
                "messages": [],
                "createdAt": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "updatedAt": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "debounceExpiresAt": datetime(2026, 1, 1, tzinfo=timezone.utc),
            },
            {
                "_id": "new",
                "tenantId": "Niyomilan",
                "clientId": "whatsapp",
                "userId": "2",
                "status": "open",
                "processing": False,
                "messages": [],
                "createdAt": datetime(2026, 3, 1, tzinfo=timezone.utc),
                "updatedAt": datetime(2026, 3, 1, tzinfo=timezone.utc),
                "debounceExpiresAt": datetime(2026, 3, 1, tzinfo=timezone.utc),
            },
        ]
    )

    deleted = await database.session_state.delete_stale_sessions(datetime(2026, 2, 1, tzinfo=timezone.utc))

    assert deleted == 1
    assert len(fake_db["session_state"].documents) == 1
    assert fake_db["session_state"].documents[0]["_id"] == "new"
