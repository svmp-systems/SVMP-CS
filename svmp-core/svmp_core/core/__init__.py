"""Core domain helpers for the SVMP runtime."""

from svmp_core.core.identity_frame import IdentityFrame
from svmp_core.core.similarity_gate import SimilarityDecision, SimilarityOutcome, evaluate_similarity

__all__ = ["IdentityFrame", "SimilarityDecision", "SimilarityOutcome", "evaluate_similarity"]
