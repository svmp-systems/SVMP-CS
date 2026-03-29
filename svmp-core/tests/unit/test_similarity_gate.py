"""Unit tests for the similarity confidence gate."""

from __future__ import annotations

import pytest

from svmp_core.core import SimilarityOutcome, evaluate_similarity


def test_similarity_gate_passes_when_score_meets_threshold() -> None:
    """Scores at or above the threshold should allow auto-answering."""

    decision = evaluate_similarity(score=0.82, threshold=0.75)

    assert decision.outcome == SimilarityOutcome.PASS
    assert decision.should_answer is True
    assert decision.should_escalate is False


def test_similarity_gate_fails_when_score_below_threshold() -> None:
    """Scores below the threshold should route to escalation."""

    decision = evaluate_similarity(score=0.62, threshold=0.75)

    assert decision.outcome == SimilarityOutcome.FAIL
    assert decision.should_answer is False
    assert decision.should_escalate is True


def test_similarity_gate_returns_no_candidate_when_candidate_missing() -> None:
    """Missing candidates should fail safely without attempting an answer."""

    decision = evaluate_similarity(score=None, threshold=0.75, candidate_found=False)

    assert decision.outcome == SimilarityOutcome.NO_CANDIDATE
    assert decision.candidate_found is False
    assert decision.should_answer is False
    assert decision.should_escalate is True


def test_similarity_gate_rejects_invalid_threshold() -> None:
    """Invalid threshold values should fail fast."""

    with pytest.raises(ValueError, match="threshold must be between 0 and 1"):
        evaluate_similarity(score=0.8, threshold=1.5)


def test_similarity_gate_rejects_invalid_score() -> None:
    """Invalid score values should fail fast."""

    with pytest.raises(ValueError, match="score must be between 0 and 1"):
        evaluate_similarity(score=-0.1, threshold=0.75)
