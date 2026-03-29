"""Core domain helpers for the SVMP runtime."""

from svmp_core.core.domain_filter import choose_domain
from svmp_core.core.escalation import (
    EscalationRequest,
    EscalationResult,
    EscalationTarget,
    request_escalation,
)
from svmp_core.core.intent_fork import IntentType, infer_intent
from svmp_core.core.governance import (
    build_answered_log,
    build_closed_log,
    build_escalated_log,
    build_governance_log,
)
from svmp_core.core.identity_frame import IdentityFrame
from svmp_core.core.similarity_gate import SimilarityDecision, SimilarityOutcome, evaluate_similarity

__all__ = [
    "IdentityFrame",
    "SimilarityDecision",
    "SimilarityOutcome",
    "EscalationRequest",
    "EscalationResult",
    "EscalationTarget",
    "IntentType",
    "build_answered_log",
    "build_closed_log",
    "build_escalated_log",
    "build_governance_log",
    "choose_domain",
    "evaluate_similarity",
    "infer_intent",
    "request_escalation",
]
