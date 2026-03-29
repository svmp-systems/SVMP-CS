"""Database contracts for the SVMP core."""

from __future__ import annotations

from svmp_core.db.base import (
    Database,
    GovernanceLogRepository,
    KnowledgeBaseRepository,
    SessionStateRepository,
    TenantRepository,
)

__all__ = [
    "Database",
    "GovernanceLogRepository",
    "KnowledgeBaseRepository",
    "MongoDatabase",
    "SessionStateRepository",
    "TenantRepository",
]


def __getattr__(name: str):
    """Load Mongo-specific adapters lazily so contract imports stay lightweight."""

    if name == "MongoDatabase":
        from svmp_core.db.mongo import MongoDatabase

        return MongoDatabase
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
