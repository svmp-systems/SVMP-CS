"""MongoDB-backed persistence implementation for SVMP."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, TypeVar

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from svmp_core.config import Settings, get_settings
from svmp_core.db.base import (
    AuditLogRepository,
    BillingSubscriptionRepository,
    Database,
    GovernanceLogRepository,
    KnowledgeBaseRepository,
    ProviderEventRepository,
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


def _serialize_document(value: Any) -> Any:
    """Recursively convert Mongo-specific values in arbitrary documents."""

    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, Mapping):
        return {key: _serialize_document(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_serialize_document(item) for item in value]
    return value


class MongoSessionStateRepository(SessionStateRepository):
    """Mongo-backed repository for active session state."""

    def __init__(self, collection, *, settings: Settings | None = None) -> None:
        self._collection = collection
        self._settings = settings or get_settings()
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
        lock_expired_before = now - timedelta(
            seconds=self._settings.WORKFLOW_B_PROCESSING_LOCK_TIMEOUT_SECONDS
        )
        document = await self._collection.find_one_and_update(
            {
                "status": "open",
                "debounceExpiresAt": {"$lte": now},
                "messages.0": {"$exists": True},
                "$or": [
                    {"processing": False},
                    {
                        "processing": True,
                        "updatedAt": {"$lt": lock_expired_before},
                    },
                ],
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
        lock_expired_before = now - timedelta(
            seconds=self._settings.WORKFLOW_B_PROCESSING_LOCK_TIMEOUT_SECONDS
        )
        document = await self._collection.find_one_and_update(
            {
                "_id": _deserialize_id(session_id),
                "status": "open",
                "debounceExpiresAt": {"$lte": now},
                "messages.0": {"$exists": True},
                "$or": [
                    {"processing": False},
                    {
                        "processing": True,
                        "updatedAt": {"$lt": lock_expired_before},
                    },
                ],
            },
            {"$set": {"processing": True, "updatedAt": now}},
            return_document=ReturnDocument.AFTER,
        )
        return _to_model(SessionState, document)

    async def delete_stale_sessions(self, before: datetime) -> int:
        result = await self._collection.delete_many({"updatedAt": {"$lt": before}})
        return result.deleted_count

    async def list_by_tenant(
        self,
        tenant_id: str,
        *,
        limit: int = 50,
    ) -> list[SessionState]:
        bounded_limit = max(1, min(limit, 100))
        cursor = self._collection.find({"tenantId": tenant_id}).sort(
            "updatedAt",
            DESCENDING,
        )
        documents = await cursor.to_list(length=bounded_limit)
        return [_to_model(SessionState, document) for document in documents if document is not None]

    async def get_by_id(
        self,
        tenant_id: str,
        session_id: str,
    ) -> SessionState | None:
        document = await self._collection.find_one(
            {
                "_id": _deserialize_id(session_id),
                "tenantId": tenant_id,
            }
        )
        return _to_model(SessionState, document)


class MongoKnowledgeBaseRepository(KnowledgeBaseRepository):
    """Mongo-backed repository for knowledge-base entries."""

    def __init__(self, collection, *, settings: Settings | None = None) -> None:
        self._collection = collection
        self._settings = settings or get_settings()
        self._alias_map = _model_alias_map(KnowledgeEntry)

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
                1 if entry.tenant_id == self._settings.SHARED_KB_TENANT_ID else 0,
                entry.question,
            )
        )
        return entries

    async def list_by_tenant(
        self,
        tenant_id: str,
        *,
        active: bool | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[KnowledgeEntry]:
        bounded_limit = max(1, min(limit, 250))
        query: dict[str, Any] = {"tenantId": tenant_id}
        if active is not None:
            query["active"] = active

        normalized_search = search.strip() if isinstance(search, str) else ""
        if normalized_search:
            escaped = re.escape(normalized_search)
            query["$or"] = [
                {"question": {"$regex": escaped, "$options": "i"}},
                {"answer": {"$regex": escaped, "$options": "i"}},
                {"tags": {"$regex": escaped, "$options": "i"}},
                {"domainId": {"$regex": escaped, "$options": "i"}},
            ]

        cursor = self._collection.find(query).sort("updatedAt", DESCENDING)
        documents = await cursor.to_list(length=bounded_limit)
        return [_to_model(KnowledgeEntry, document) for document in documents if document is not None]

    async def create(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        payload = entry.model_dump(by_alias=True, exclude_none=True)
        result = await self._collection.insert_one(payload)
        payload["_id"] = _serialize_id(result.inserted_id)
        return KnowledgeEntry(**payload)

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

    async def update_by_id(
        self,
        tenant_id: str,
        entry_id: str,
        data: Mapping[str, Any],
    ) -> KnowledgeEntry | None:
        update_payload = {
            self._alias_map.get(key, key): _to_storage_value(value)
            for key, value in data.items()
        }
        document = await self._collection.find_one_and_update(
            {
                "_id": _deserialize_id(entry_id),
                "tenantId": tenant_id,
            },
            {"$set": update_payload},
            return_document=ReturnDocument.AFTER,
        )
        return _to_model(KnowledgeEntry, document)

    async def deactivate_by_id(
        self,
        tenant_id: str,
        entry_id: str,
        data: Mapping[str, Any],
    ) -> KnowledgeEntry | None:
        return await self.update_by_id(
            tenant_id,
            entry_id,
            {
                **dict(data),
                "active": False,
            },
        )


class MongoGovernanceLogRepository(GovernanceLogRepository):
    """Mongo-backed repository for immutable governance logs."""

    def __init__(self, collection) -> None:
        self._collection = collection

    async def create(self, log: GovernanceLog) -> GovernanceLog:
        payload = log.model_dump(by_alias=True, exclude_none=True)
        result = await self._collection.insert_one(payload)
        payload["_id"] = _serialize_id(result.inserted_id)
        return GovernanceLog(**payload)

    async def list_by_tenant(
        self,
        tenant_id: str,
        *,
        limit: int = 100,
    ) -> list[GovernanceLog]:
        bounded_limit = max(1, min(limit, 250))
        cursor = self._collection.find({"tenantId": tenant_id}).sort(
            "timestamp",
            DESCENDING,
        )
        documents = await cursor.to_list(length=bounded_limit)
        return [_to_model(GovernanceLog, document) for document in documents if document is not None]

    async def count_by_decision(self, tenant_id: str) -> Mapping[str, int]:
        cursor = self._collection.aggregate(
            [
                {"$match": {"tenantId": tenant_id}},
                {"$group": {"_id": "$decision", "count": {"$sum": 1}}},
            ]
        )
        rows = await cursor.to_list(length=None)
        counts: dict[str, int] = {}
        for row in rows:
            decision = row.get("_id") if isinstance(row, Mapping) else None
            count = row.get("count") if isinstance(row, Mapping) else None
            if isinstance(decision, str) and isinstance(count, int):
                counts[decision] = count
        return counts


class MongoAuditLogRepository(AuditLogRepository):
    """Mongo-backed repository for dashboard administrative audit logs."""

    def __init__(self, collection) -> None:
        self._collection = collection

    async def create(self, log: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = _to_storage_value(dict(log))
        result = await self._collection.insert_one(payload)
        payload["_id"] = _serialize_id(result.inserted_id)
        return _serialize_document(payload)


class MongoBillingSubscriptionRepository(BillingSubscriptionRepository):
    """Mongo-backed repository for Stripe subscription state."""

    def __init__(self, collection) -> None:
        self._collection = collection

    async def get_by_tenant_id(self, tenant_id: str) -> Mapping[str, Any] | None:
        document = await self._collection.find_one({"tenantId": tenant_id})
        return _serialize_document(document) if isinstance(document, Mapping) else None

    async def upsert_by_tenant_id(
        self,
        tenant_id: str,
        data: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        payload = {
            **_to_storage_value(dict(data)),
            "tenantId": tenant_id,
        }
        document = await self._collection.find_one_and_update(
            {"tenantId": tenant_id},
            {"$set": payload},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return _serialize_document(document) if isinstance(document, Mapping) else None

    async def get_by_stripe_ids(
        self,
        *,
        stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        query: dict[str, Any] = {}
        if stripe_subscription_id:
            query["stripeSubscriptionId"] = stripe_subscription_id
        elif stripe_customer_id:
            query["stripeCustomerId"] = stripe_customer_id
        else:
            return None

        document = await self._collection.find_one(query)
        return _serialize_document(document) if isinstance(document, Mapping) else None


class MongoProviderEventRepository(ProviderEventRepository):
    """Mongo-backed idempotency records for provider webhooks."""

    def __init__(self, collection) -> None:
        self._collection = collection

    async def record_once(
        self,
        *,
        provider: str,
        event_id: str,
        event_type: str,
        tenant_id: str | None,
        payload_hash: str,
    ) -> bool:
        try:
            await self._collection.insert_one(
                {
                    "provider": provider,
                    "eventId": event_id,
                    "eventType": event_type,
                    "tenantId": tenant_id,
                    "payloadHash": payload_hash,
                    "processedAt": datetime.now(timezone.utc),
                }
            )
        except DuplicateKeyError:
            return False
        return True


class MongoTenantRepository(TenantRepository):
    """Mongo-backed repository for tenant metadata."""

    def __init__(
        self,
        collection,
        *,
        verified_users_collection=None,
        billing_subscriptions_collection=None,
        integration_status_collection=None,
    ) -> None:
        self._collection = collection
        self._verified_users_collection = verified_users_collection
        self._billing_subscriptions_collection = billing_subscriptions_collection
        self._integration_status_collection = integration_status_collection

    async def get_by_tenant_id(self, tenant_id: str) -> Mapping[str, Any] | None:
        document = await self._collection.find_one({"tenantId": tenant_id})
        if document is None:
            return None
        normalized = deepcopy(document)
        if "_id" in normalized:
            normalized["_id"] = _serialize_id(normalized["_id"])
        return normalized

    async def update_by_tenant_id(
        self,
        tenant_id: str,
        data: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        update_payload = _to_storage_value(dict(data))
        if not update_payload:
            return await self.get_by_tenant_id(tenant_id)

        document = await self._collection.find_one_and_update(
            {"tenantId": tenant_id},
            {"$set": update_payload},
            return_document=ReturnDocument.AFTER,
        )
        return _serialize_document(document) if isinstance(document, Mapping) else None

    async def upsert_tenant(self, tenant_document: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = deepcopy(dict(tenant_document))
        tenant_id = payload.get("tenantId")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise DatabaseError("tenant document missing tenantId")

        document = await self._collection.find_one_and_update(
            {"tenantId": tenant_id.strip()},
            {"$set": _to_storage_value(payload)},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if not isinstance(document, Mapping):
            raise DatabaseError("failed to persist tenant document")
        return _serialize_document(document)

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

    async def resolve_dashboard_tenant_context(
        self,
        *,
        auth_provider: str = "clerk",
        provider_user_id: str | None = None,
        email: str | None = None,
        clerk_organization_id: str | None = None,
        clerk_user_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        if self._verified_users_collection is None:
            return None

        provider = auth_provider.strip().lower() if isinstance(auth_provider, str) else "clerk"
        user_id = (
            provider_user_id
            if isinstance(provider_user_id, str) and provider_user_id.strip()
            else clerk_user_id
        )
        normalized_user_id = user_id.strip() if isinstance(user_id, str) else ""
        normalized_email = email.strip().lower() if isinstance(email, str) and email.strip() else ""
        if not normalized_user_id and not normalized_email:
            return None

        membership = None
        if normalized_user_id:
            membership = await self._verified_users_collection.find_one(
                {
                    "authProvider": provider,
                    "providerUserId": normalized_user_id,
                    "status": "active",
                }
            )
            if not isinstance(membership, Mapping):
                membership = await self._verified_users_collection.find_one(
                    {
                        "clerkUserId": normalized_user_id,
                        "status": "active",
                    }
                )

        if not isinstance(membership, Mapping) and normalized_email:
            membership = await self._verified_users_collection.find_one(
                {
                    "email": normalized_email,
                    "status": {"$in": ["active", "invited"]},
                },
                sort=[("status", ASCENDING), ("updatedAt", DESCENDING)],
            )

            if isinstance(membership, Mapping) and normalized_user_id and not membership.get("providerUserId"):
                membership = await self._verified_users_collection.find_one_and_update(
                    {"_id": membership["_id"]},
                    {
                        "$set": {
                            "authProvider": provider,
                            "providerUserId": normalized_user_id,
                            "status": "active",
                            "acceptedAt": datetime.now(timezone.utc),
                            "updatedAt": datetime.now(timezone.utc),
                        }
                    },
                    return_document=ReturnDocument.AFTER,
                )

        if not isinstance(membership, Mapping):
            return None

        tenant_id = membership.get("tenantId")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            return None
        normalized_tenant_id = tenant_id.strip()

        tenant = await self.get_by_tenant_id(normalized_tenant_id)
        billing_subscription = None
        if self._billing_subscriptions_collection is not None:
            billing_subscription = await self._billing_subscriptions_collection.find_one(
                {"tenantId": normalized_tenant_id}
            )

        tenant_billing = tenant.get("billing", {}) if isinstance(tenant, Mapping) else {}
        if not isinstance(tenant_billing, Mapping):
            tenant_billing = {}

        subscription_status = None
        if isinstance(billing_subscription, Mapping):
            subscription_status = billing_subscription.get("status")
        if subscription_status is None:
            subscription_status = tenant_billing.get("status")

        tenant_name = None
        if isinstance(tenant, Mapping):
            raw_name = tenant.get("tenantName")
            if isinstance(raw_name, str):
                tenant_name = raw_name

        return {
            "tenantId": normalized_tenant_id,
            "tenantName": tenant_name,
            "role": membership.get("role", "viewer"),
            "email": membership.get("email"),
            "organizationId": membership.get("organizationId") or normalized_tenant_id,
            "permissions": membership.get("permissions", []),
            "subscriptionStatus": subscription_status or "none",
            "billing": dict(tenant_billing),
        }

    async def list_integration_status(
        self,
        tenant_id: str,
    ) -> list[Mapping[str, Any]]:
        if self._integration_status_collection is None:
            return []

        cursor = self._integration_status_collection.find({"tenantId": tenant_id})
        documents = await cursor.to_list(length=50)
        return [
            _serialize_document(document)
            for document in documents
            if isinstance(document, Mapping)
        ]

    async def update_integration_status(
        self,
        tenant_id: str,
        provider: str,
        data: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        if self._integration_status_collection is None:
            return None

        update_payload = {
            **_to_storage_value(dict(data)),
            "tenantId": tenant_id,
            "provider": provider,
        }
        document = await self._integration_status_collection.find_one_and_update(
            {
                "tenantId": tenant_id,
                "provider": provider,
            },
            {"$set": update_payload},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return _serialize_document(document) if isinstance(document, Mapping) else None


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
        self._audit_logs_repo: MongoAuditLogRepository | None = None
        self._billing_subscriptions_repo: MongoBillingSubscriptionRepository | None = None
        self._provider_events_repo: MongoProviderEventRepository | None = None

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

    @property
    def audit_logs(self) -> AuditLogRepository:
        if self._audit_logs_repo is None:
            raise DatabaseError("database not connected")
        return self._audit_logs_repo

    @property
    def billing_subscriptions(self) -> BillingSubscriptionRepository:
        if self._billing_subscriptions_repo is None:
            raise DatabaseError("database not connected")
        return self._billing_subscriptions_repo

    @property
    def provider_events(self) -> ProviderEventRepository:
        if self._provider_events_repo is None:
            raise DatabaseError("database not connected")
        return self._provider_events_repo

    async def connect(self) -> None:
        try:
            if self._client is None:
                self._client = AsyncIOMotorClient(self._settings.MONGODB_URI)

            self._db = self._client[self._settings.MONGODB_DB_NAME]
            await self._ensure_indexes()

            self._session_state_repo = MongoSessionStateRepository(
                self._db[self._settings.MONGODB_SESSION_COLLECTION],
                settings=self._settings,
            )
            self._knowledge_base_repo = MongoKnowledgeBaseRepository(
                self._db[self._settings.MONGODB_KB_COLLECTION],
                settings=self._settings,
            )
            self._governance_logs_repo = MongoGovernanceLogRepository(
                self._db[self._settings.MONGODB_GOVERNANCE_COLLECTION]
            )
            self._tenants_repo = MongoTenantRepository(
                self._db[self._settings.MONGODB_TENANTS_COLLECTION],
                verified_users_collection=self._db[
                    self._settings.MONGODB_VERIFIED_USERS_COLLECTION
                ],
                billing_subscriptions_collection=self._db[
                    self._settings.MONGODB_BILLING_SUBSCRIPTIONS_COLLECTION
                ],
                integration_status_collection=self._db[
                    self._settings.MONGODB_INTEGRATION_STATUS_COLLECTION
                ],
            )
            self._audit_logs_repo = MongoAuditLogRepository(
                self._db[self._settings.MONGODB_AUDIT_LOGS_COLLECTION]
            )
            self._billing_subscriptions_repo = MongoBillingSubscriptionRepository(
                self._db[self._settings.MONGODB_BILLING_SUBSCRIPTIONS_COLLECTION]
            )
            self._provider_events_repo = MongoProviderEventRepository(
                self._db[self._settings.MONGODB_PROVIDER_EVENTS_COLLECTION]
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
            self._audit_logs_repo = None
            self._billing_subscriptions_repo = None
            self._provider_events_repo = None

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

        verified_users_collection = self._db[self._settings.MONGODB_VERIFIED_USERS_COLLECTION]
        await verified_users_collection.create_index(
            [("authProvider", ASCENDING), ("providerUserId", ASCENDING)],
            unique=True,
            name="verified_user_provider_unique",
            partialFilterExpression={
                "authProvider": {"$exists": True, "$type": "string"},
                "providerUserId": {"$exists": True, "$type": "string"},
            },
        )
        await verified_users_collection.create_index(
            [("email", ASCENDING), ("status", ASCENDING)],
            name="verified_user_email_status",
        )
        await verified_users_collection.create_index(
            [("tenantId", ASCENDING), ("role", ASCENDING)],
            name="verified_user_tenant_role",
        )

        billing_collection = self._db[self._settings.MONGODB_BILLING_SUBSCRIPTIONS_COLLECTION]
        await billing_collection.create_index(
            [("tenantId", ASCENDING)],
            unique=True,
            name="billing_tenant_unique",
            partialFilterExpression={
                "tenantId": {"$exists": True, "$type": "string"},
            },
        )
        await billing_collection.create_index(
            [("stripeCustomerId", ASCENDING)],
            name="billing_stripe_customer",
        )
        await billing_collection.create_index(
            [("stripeSubscriptionId", ASCENDING)],
            name="billing_stripe_subscription",
        )

        integration_collection = self._db[self._settings.MONGODB_INTEGRATION_STATUS_COLLECTION]
        await integration_collection.create_index(
            [("tenantId", ASCENDING), ("provider", ASCENDING)],
            unique=True,
            name="integration_tenant_provider_unique",
            partialFilterExpression={
                "tenantId": {"$exists": True, "$type": "string"},
                "provider": {"$exists": True, "$type": "string"},
            },
        )

        audit_collection = self._db[self._settings.MONGODB_AUDIT_LOGS_COLLECTION]
        await audit_collection.create_index(
            [("tenantId", ASCENDING), ("timestamp", ASCENDING)],
            name="audit_tenant_timestamp",
        )
        await audit_collection.create_index(
            [("tenantId", ASCENDING), ("action", ASCENDING)],
            name="audit_tenant_action",
        )
        await audit_collection.create_index(
            [("tenantId", ASCENDING), ("resourceType", ASCENDING), ("resourceId", ASCENDING)],
            name="audit_tenant_resource",
        )

        provider_events_collection = self._db[self._settings.MONGODB_PROVIDER_EVENTS_COLLECTION]
        await provider_events_collection.create_index(
            [("provider", ASCENDING), ("eventId", ASCENDING)],
            unique=True,
            name="provider_event_unique",
            partialFilterExpression={
                "provider": {"$exists": True, "$type": "string"},
                "eventId": {"$exists": True, "$type": "string"},
            },
        )
        await provider_events_collection.create_index(
            [("tenantId", ASCENDING), ("processedAt", ASCENDING)],
            name="provider_events_tenant_processed",
        )
