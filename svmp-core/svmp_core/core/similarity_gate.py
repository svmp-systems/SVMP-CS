"""Confidence gate helpers for FAQ-match decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SimilarityOutcome(StrEnum):
    """Possible outcomes from the similarity confidence gate."""

    PASS = "pass"
    FAIL = "fail"
    NO_CANDIDATE = "no_candidate"


@dataclass(frozen=True)
class SimilarityDecision:
    """Normalized result of evaluating a score against a threshold."""

    outcome: SimilarityOutcome
    score: float | None
    threshold: float
    candidate_found: bool
    reason: str

    @property
    def should_answer(self) -> bool:
        """Whether the current score is strong enough for auto-answering."""

        return self.outcome == SimilarityOutcome.PASS

    @property
    def should_escalate(self) -> bool:
        """Whether the current score should fall back to escalation."""

        return not self.should_answer


def evaluate_similarity(
    score: float | None,
    threshold: float,
    *,
    candidate_found: bool = True,
) -> SimilarityDecision:
    """Evaluate whether a candidate match is safe to auto-answer."""

    _validate_threshold(threshold)
    _validate_score(score)

    if not candidate_found or score is None:
        return SimilarityDecision(
            outcome=SimilarityOutcome.NO_CANDIDATE,
            score=score,
            threshold=threshold,
            candidate_found=False,
            reason="no candidate match available",
        )

    if score >= threshold:
        return SimilarityDecision(
            outcome=SimilarityOutcome.PASS,
            score=score,
            threshold=threshold,
            candidate_found=True,
            reason="score meets or exceeds threshold",
        )

    return SimilarityDecision(
        outcome=SimilarityOutcome.FAIL,
        score=score,
        threshold=threshold,
        candidate_found=True,
        reason="score below threshold",
    )


def _validate_threshold(threshold: float) -> None:
    """Reject impossible threshold values."""

    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")


def _validate_score(score: float | None) -> None:
    """Reject impossible similarity scores."""

    if score is None:
        return
    if not 0 <= score <= 1:
        raise ValueError("score must be between 0 and 1")
