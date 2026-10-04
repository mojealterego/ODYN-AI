"""Deterministic policy tests for cognition review decisions."""

import pytest

from agent.cognition.contracts import ReviewAction, ReviewDecision
from agent.cognition.gate_policy import classify_review_decision


def _decision(action: ReviewAction, *, evidence: tuple[str, ...] = ()) -> ReviewDecision:
    return ReviewDecision(
        action=action,
        confidence=0.8,
        reason=f"{action.value} reason",
        required_evidence=evidence,
    )


def test_accept_is_the_only_execution_allowed_action():
    verdict = classify_review_decision(_decision(ReviewAction.ACCEPT))

    assert verdict.allows_execution is True
    assert verdict.retryable is False
    assert verdict.escalated is False


@pytest.mark.parametrize(
    "action",
    [ReviewAction.CORRECT, ReviewAction.RETRY, ReviewAction.RETRIEVE_EVIDENCE],
)
def test_recoverable_review_actions_block_execution_and_remain_retryable(action: ReviewAction):
    verdict = classify_review_decision(_decision(action))

    assert verdict.allows_execution is False
    assert verdict.retryable is True
    assert verdict.escalated is False
    assert verdict.decision.action is action


def test_retrieve_evidence_feedback_names_required_evidence():
    verdict = classify_review_decision(
        _decision(
            ReviewAction.RETRIEVE_EVIDENCE,
            evidence=("current upstream commit", "verification result"),
        )
    )

    assert "current upstream commit" in verdict.feedback
    assert "verification result" in verdict.feedback


def test_escalate_blocks_execution_and_is_terminal():
    verdict = classify_review_decision(_decision(ReviewAction.ESCALATE))

    assert verdict.allows_execution is False
    assert verdict.retryable is False
    assert verdict.escalated is True
