"""Unit tests for the bounded candidate review cycle."""

import pytest

from agent.cognition import ReviewAction, ReviewDecision
from agent.cognition.review_cycle import (
    ReviewCycleState,
    advance_review_cycle,
    build_review_feedback,
)


def _decision(action: ReviewAction) -> ReviewDecision:
    return ReviewDecision(
        action=action,
        confidence=0.9,
        reason="reason",
        corrections=("fix",) if action is ReviewAction.CORRECT else (),
        required_evidence=("source",)
        if action is ReviewAction.RETRIEVE_EVIDENCE
        else (),
    )


def test_retry_then_accept_records_both_attempts():
    outcome = advance_review_cycle(
        ReviewCycleState(),
        _decision(ReviewAction.RETRY),
        max_attempts=3,
        max_corrections=2,
    )
    assert outcome.action == "retry"
    assert outcome.state.attempts == 1

    accepted = advance_review_cycle(
        outcome.state,
        _decision(ReviewAction.ACCEPT),
        max_attempts=3,
        max_corrections=2,
    )
    assert accepted.action == "accept"
    assert accepted.state.attempts == 2


def test_attempt_limit_exhausts_without_an_extra_retry():
    state = advance_review_cycle(
        ReviewCycleState(),
        _decision(ReviewAction.RETRY),
        max_attempts=2,
        max_corrections=2,
    ).state
    exhausted = advance_review_cycle(
        state,
        _decision(ReviewAction.RETRY),
        max_attempts=2,
        max_corrections=2,
    )
    assert exhausted.action == "terminal"
    assert exhausted.exhausted is True
    assert exhausted.state.attempts == 2


def test_correction_limit_exhausts_only_after_budget_is_exceeded():
    first = advance_review_cycle(
        ReviewCycleState(),
        _decision(ReviewAction.CORRECT),
        max_attempts=4,
        max_corrections=1,
    )
    assert first.action == "retry"
    assert first.state.corrections == 1

    second = advance_review_cycle(
        first.state,
        _decision(ReviewAction.CORRECT),
        max_attempts=4,
        max_corrections=1,
    )
    assert second.action == "terminal"
    assert second.exhausted is True
    assert second.state.corrections == 2


def test_escalate_is_terminal_without_marking_budget_exhaustion():
    outcome = advance_review_cycle(
        ReviewCycleState(),
        _decision(ReviewAction.ESCALATE),
        max_attempts=3,
        max_corrections=2,
    )
    assert outcome.action == "terminal"
    assert outcome.exhausted is False


@pytest.mark.parametrize(
    ("attempts", "corrections"),
    [(0, 0), (-1, 0), (1, -1)],
)
def test_invalid_cycle_limits_are_rejected(attempts: int, corrections: int):
    with pytest.raises(ValueError):
        advance_review_cycle(
            ReviewCycleState(),
            _decision(ReviewAction.RETRY),
            max_attempts=attempts,
            max_corrections=corrections,
        )


def test_feedback_is_bounded_fixed_wrapper_with_json_data():
    text = build_review_feedback(_decision(ReviewAction.RETRIEVE_EVIDENCE))
    assert "untrusted review data" in text.lower()
    assert '"action": "retrieve_evidence"' in text
    assert '"source"' in text
    assert "does not override system policy" in text
