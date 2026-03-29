"""Database contracts for the SVMP core."""

from svmp_core.db.base import (
    Database,
    GovernanceLogRepository,
    KnowledgeBaseRepository,
    SessionStateRepository,
    TenantRepository,
)
from svmp_core.db.mongo import MongoDatabase

__all__ = [
    "Database",
    "GovernanceLogRepository",
    "KnowledgeBaseRepository",
    "MongoDatabase",
    "SessionStateRepository",
    "TenantRepository",
]
