"""MongoDB-backed persistence implementation for SVMP."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from typing import Any, TypeVar

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from pymongo import ASCENDING, ReturnDocument

from svmp_core.config import Settings, get_settings
from svmp_core.db.base import (
    Database,
    GovernanceLogRepository,
    KnowledgeBaseRepository,
    SessionStateRepository,
    TenantRepository,
)
from svmp_core.exceptions import DatabaseError
from svmp_core.models.governance import GovernanceLog
from svmp_core.models.knowledge import KnowledgeEntry
from svmp_core.models.session import SessionState

ModelT = TypeVar("ModelT", bound=BaseModel)


def _serialize_id(value: Any) -> Any:
    """Convert Mongo object IDs to string form for app models."""

    if isinstance(value, ObjectId):
        return str(value)
    return value


def _deserialize_id(value: str) -> ObjectId | str:
    """Convert string IDs back to ObjectId when possible."""

    if ObjectId.is_valid(value):
        return ObjectId(value)
    return value


def _model_alias_map(model_cls: type[BaseModel]) -> dict[str, str]:
    """Return a top-level snake_case to alias map for a Pydantic model."""

    alias_map: dict[str, str] = {}
    for name, field in model_cls.model_fields.items():
        alias_map[name] = field.alias or name
    return alias_map


def _to_storage_value(value: Any) -> Any:
    """Recursively convert models and nested values into Mongo-safe payloads."""

    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True, exclude_none=True)
    if isinstance(value, Mapping):
        return {key: _to_storage_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_to_storage_value(item) for item in value]
    return value


def _to_model(model_cls: type[ModelT], document: Mapping[str, Any] | None) -> ModelT | None:
    """Convert a Mongo document into an app model."""

    if document is None:
        return None

    normalized = dict(document)
    if "_id" in normalized:
        normalized["_id"] = _serialize_id(normalized["_id"])
    return model_cls(**normalized)


class MongoSessionStateRepository(SessionStateRepository):
    """Mongo-backed repository for active session state."""

    def __init__(self, collection) -> None:
        self._collection = collection
        self._alias_map = _model_alias_map(SessionState)

    async def get_by_identity(
        self,
        tenant_id: str,
        client_id: str,
        user_id: str,
    ) -> SessionState | None:
        document = await self._collection.find_one(
            {
                "tenantId": tenant_id,
                "clientId": client_id,
                "userId": user_id,
            }
        )
        return _to_model(SessionState, document)

    async def create(self, session: SessionState) -> SessionState:
        payload = session.model_dump(by_alias=True, exclude_none=True)
        result = await self._collection.insert_one(payload)
        payload["_id"] = _serialize_id(result.inserted_id)
        return SessionState(**payload)

    async def update_by_id(
        self,
        session_id: str,
        data: Mapping[str, Any],
    ) -> SessionState | None:
        update_payload = {
            self._alias_map.get(key, key): _to_storage_value(value)
            for key, value in data.items()
        }
        document = await self._collection.find_one_and_update(
            {"_id": _deserialize_id(session_id)},
            {"$set": update_payload},
            return_document=ReturnDocument.AFTER,
        )
        return _to_model(SessionState, document)

    async def acquire_ready_session(self, now: datetime) -> SessionState | None:
        document = await self._collection.find_one_and_update(
            {
                "status": "open",
                "processing": False,
                "debounceExpiresAt": {"$lte": now},
            },
            {"$set": {"processing": True, "updatedAt": now}},
            sort=[("debounceExpiresAt", ASCENDING)],
            return_document=ReturnDocument.AFTER,
        )
        return _to_model(SessionState, document)

    async def acquire_ready_session_by_id(
        self,
        session_id: str,
        now: datetime,
    ) -> SessionState | None:
        document = await self._collection.find_one_and_update(
            {
                "_id": _deserialize_id(session_id),
                "status": "open",
                "processing": False,
                "debounceExpiresAt": {"$lte": now},
            },
            {"$set": {"processing": True, "updatedAt": now}},
            return_document=ReturnDocument.AFTER,
        )
        return _to_model(SessionState, document)

    async def delete_stale_sessions(self, before: datetime) -> int:
        result = await self._collection.delete_many({"updatedAt": {"$lt": before}})
        return result.deleted_count


class MongoKnowledgeBaseRepository(KnowledgeBaseRepository):
    """Mongo-backed repository for knowledge-base entries."""

    def __init__(self, collection, *, settings: Settings | None = None) -> None:
        self._collection = collection
        self._settings = settings or get_settings()

    async def list_active_by_tenant_and_domain(
        self,
        tenant_id: str,
        domain_id: str,
    ) -> list[KnowledgeEntry]:
        cursor = self._collection.find(
            {
                "tenantId": {
                    "$in": [
                        tenant_id,
                        self._settings.SHARED_KB_TENANT_ID,
                    ]
                },
                "domainId": domain_id,
                "active": True,
            }
        )
        documents = await cursor.to_list(length=None)
        entries = [_to_model(KnowledgeEntry, document) for document in documents if document is not None]
        entries.sort(
            key=lambda entry: (
                1
                if entry is not None and entry.tenant_id == self._settings.SHARED_KB_TENANT_ID
                else 0,
                entry.question if entry is not None else "",
            )
        )
        return entries

    async def replace_entries_for_tenant_domain(
        self,
        tenant_id: str,
        domain_id: str,
        entries: Sequence[KnowledgeEntry],
    ) -> int:
        await self._collection.delete_many(
            {
                "tenantId": tenant_id,
                "domainId": domain_id,
            }
        )
        if not entries:
            return 0

        payloads = [
            entry.model_dump(by_alias=True, exclude_none=True)
            for entry in entries
        ]
        result = await self._collection.insert_many(payloads)
        return len(result.inserted_ids)


class MongoGovernanceLogRepository(GovernanceLogRepository):
    """Mongo-backed repository for immutable governance logs."""

    def __init__(self, collection) -> None:
        self._collection = collection

    async def create(self, log: GovernanceLog) -> GovernanceLog:
        payload = log.model_dump(by_alias=True, exclude_none=True)
        result = await self._collection.insert_one(payload)
        payload["_id"] = _serialize_id(result.inserted_id)
        return GovernanceLog(**payload)


class MongoTenantRepository(TenantRepository):
    """Mongo-backed repository for tenant metadata."""

    def __init__(self, collection) -> None:
        self._collection = collection

    async def get_by_tenant_id(self, tenant_id: str) -> Mapping[str, Any] | None:
        document = await self._collection.find_one({"tenantId": tenant_id})
        if document is None:
            return None
        normalized = deepcopy(document)
        if "_id" in normalized:
            normalized["_id"] = _serialize_id(normalized["_id"])
        return normalized

    async def upsert_tenant(self, tenant_document: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = deepcopy(dict(tenant_document))
        tenant_id = payload.get("tenantId")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise DatabaseError("tenant document missing tenantId")

        await self._collection.replace_one(
            {"tenantId": tenant_id.strip()},
            payload,
            upsert=True,
        )
        stored = await self.get_by_tenant_id(tenant_id.strip())
        if stored is None:
            raise DatabaseError("failed to persist tenant document")
        return stored

    async def resolve_tenant_id_for_provider(
        self,
        *,
        provider: str,
        identities: Sequence[str],
    ) -> str | None:
        normalized_identities = [identity.strip() for identity in identities if isinstance(identity, str) and identity.strip()]
        if not normalized_identities:
            return None

        field_map = {
            "meta": [
                "channels.meta.phoneNumberIds",
                "channels.meta.displayNumbers",
            ],
            "twilio": [
                "channels.twilio.whatsappNumbers",
                "channels.twilio.accountSids",
            ],
        }
        fields = field_map.get(provider.strip().lower())
        if not fields:
            return None

        query = {
            "$or": [
                {field: identity}
                for field in fields
                for identity in normalized_identities
            ]
        }
        cursor = self._collection.find(query)
        documents = await cursor.to_list(length=2)
        if not documents:
            return None

        tenant_ids = {
            str(document.get("tenantId")).strip()
            for document in documents
            if isinstance(document, Mapping) and isinstance(document.get("tenantId"), str) and str(document.get("tenantId")).strip()
        }
        if len(tenant_ids) != 1:
            raise DatabaseError("tenant resolution is ambiguous for provider payload")

        return next(iter(tenant_ids))


class MongoDatabase(Database):
    """Top-level Mongo database adapter that wires all repositories."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: AsyncIOMotorClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._db = None
        self._session_state_repo: MongoSessionStateRepository | None = None
        self._knowledge_base_repo: MongoKnowledgeBaseRepository | None = None
        self._governance_logs_repo: MongoGovernanceLogRepository | None = None
        self._tenants_repo: MongoTenantRepository | None = None

    @property
    def session_state(self) -> SessionStateRepository:
        if self._session_state_repo is None:
            raise DatabaseError("database not connected")
        return self._session_state_repo

    @property
    def knowledge_base(self) -> KnowledgeBaseRepository:
        if self._knowledge_base_repo is None:
            raise DatabaseError("database not connected")
        return self._knowledge_base_repo

    @property
    def governance_logs(self) -> GovernanceLogRepository:
        if self._governance_logs_repo is None:
            raise DatabaseError("database not connected")
        return self._governance_logs_repo

    @property
    def tenants(self) -> TenantRepository:
        if self._tenants_repo is None:
            raise DatabaseError("database not connected")
        return self._tenants_repo

    async def connect(self) -> None:
        try:
            if self._client is None:
                self._client = AsyncIOMotorClient(self._settings.MONGODB_URI)

            self._db = self._client[self._settings.MONGODB_DB_NAME]
            await self._ensure_indexes()

            self._session_state_repo = MongoSessionStateRepository(
                self._db[self._settings.MONGODB_SESSION_COLLECTION]
            )
            self._knowledge_base_repo = MongoKnowledgeBaseRepository(
                self._db[self._settings.MONGODB_KB_COLLECTION],
                settings=self._settings,
            )
            self._governance_logs_repo = MongoGovernanceLogRepository(
                self._db[self._settings.MONGODB_GOVERNANCE_COLLECTION]
            )
            self._tenants_repo = MongoTenantRepository(
                self._db[self._settings.MONGODB_TENANTS_COLLECTION]
            )
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise DatabaseError("failed to connect to MongoDB") from exc

    async def disconnect(self) -> None:
        try:
            if self._client is not None:
                self._client.close()
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise DatabaseError("failed to disconnect from MongoDB") from exc
        finally:
            self._db = None
            self._session_state_repo = None
            self._knowledge_base_repo = None
            self._governance_logs_repo = None
            self._tenants_repo = None

    async def _ensure_indexes(self) -> None:
        """Create the minimum indexes required by the current workflows."""

        if self._db is None:
            raise DatabaseError("database not connected")

        session_collection = self._db[self._settings.MONGODB_SESSION_COLLECTION]
        await session_collection.create_index(
            [("tenantId", ASCENDING), ("clientId", ASCENDING), ("userId", ASCENDING)],
            unique=True,
            name="session_identity_unique",
        )
        await session_collection.create_index(
            [("processing", ASCENDING), ("debounceExpiresAt", ASCENDING)],
            name="session_ready_lookup",
        )

        kb_collection = self._db[self._settings.MONGODB_KB_COLLECTION]
        await kb_collection.create_index(
            [("tenantId", ASCENDING), ("domainId", ASCENDING), ("active", ASCENDING)],
            name="knowledge_lookup",
        )

        governance_collection = self._db[self._settings.MONGODB_GOVERNANCE_COLLECTION]
        await governance_collection.create_index(
            [("tenantId", ASCENDING), ("timestamp", ASCENDING)],
            name="governance_tenant_timestamp",
        )

        tenants_collection = self._db[self._settings.MONGODB_TENANTS_COLLECTION]
        await tenants_collection.create_index(
            [("tenantId", ASCENDING)],
            unique=True,
            name="tenant_id_unique",
            partialFilterExpression={
                "tenantId": {
                    "$exists": True,
                    "$type": "string",
                }
            },
        )
