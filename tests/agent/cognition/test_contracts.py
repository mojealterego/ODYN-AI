"""Characterization tests for the neutral cognition review contracts."""

from dataclasses import FrozenInstanceError

import pytest

from agent.cognition.contracts import (
    CandidateReviewer,
    CandidateSnapshot,
    ReviewAction,
    ReviewContext,
    ReviewDecision,
)


def test_review_action_preserves_gate_semantics():
    assert {action.value for action in ReviewAction} == {
        "accept",
        "correct",
        "retry",
        "retrieve_evidence",
        "escalate",
    }


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_review_decision_rejects_out_of_range_confidence(confidence: float):
    with pytest.raises(ValueError, match="confidence"):
        ReviewDecision(
            action=ReviewAction.ACCEPT,
            confidence=confidence,
            reason="reviewed",
        )


def test_review_decision_preserves_structured_feedback():
    decision = ReviewDecision(
        action=ReviewAction.RETRIEVE_EVIDENCE,
        confidence=0.72,
        reason="Missing current source.",
        issues=("source_stale",),
        corrections=("Re-check against current source.",),
        required_evidence=("current upstream state",),
    )

    assert decision.action is ReviewAction.RETRIEVE_EVIDENCE
    assert decision.issues == ("source_stale",)
    assert decision.corrections == ("Re-check against current source.",)
    assert decision.required_evidence == ("current upstream state",)


def test_candidate_and_context_are_frozen_snapshots():
    candidate = CandidateSnapshot(
        content="Inspect repository.",
        tool_calls=({"id": "call-1", "name": "read_file", "arguments": "{}"},),
        finish_reason="tool_calls",
    )
    context = ReviewContext(
        task_id="task-1",
        session_id="session-1",
        messages=({"role": "user", "content": "Inspect repository."},),
    )

    with pytest.raises(FrozenInstanceError):
        candidate.content = "mutated"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        context.task_id = "mutated"  # type: ignore[misc]


def test_candidate_reviewer_protocol_shape():
    class Reviewer:
        def review(self, candidate: CandidateSnapshot, *, context: ReviewContext) -> ReviewDecision:
            assert candidate.content == "candidate"
            assert context.task_id == "task-1"
            return ReviewDecision(
                action=ReviewAction.ACCEPT,
                confidence=1.0,
                reason="accepted",
            )

    reviewer: CandidateReviewer = Reviewer()
    result = reviewer.review(
        CandidateSnapshot(content="candidate"),
        context=ReviewContext(task_id="task-1"),
    )
    assert result.action is ReviewAction.ACCEPT
