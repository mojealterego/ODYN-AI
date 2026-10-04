"""Deterministic execution policy for cognition review decisions.

The reviewer may be model-driven; this module is not. It translates a typed
ReviewDecision into an execution verdict. Only ACCEPT may pass this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import ReviewAction, ReviewDecision


@dataclass(frozen=True)
class ReviewGateVerdict:
    """Deterministic execution disposition for one review decision."""

    allows_execution: bool
    retryable: bool
    escalated: bool
    feedback: str
    decision: ReviewDecision


def classify_review_decision(decision: ReviewDecision) -> ReviewGateVerdict:
    """Map structured review output to a deterministic execution policy."""
    if decision.action is ReviewAction.ACCEPT:
        return ReviewGateVerdict(
            allows_execution=True,
            retryable=False,
            escalated=False,
            feedback=decision.reason,
            decision=decision,
        )

    if decision.action in {
        ReviewAction.CORRECT,
        ReviewAction.RETRY,
        ReviewAction.RETRIEVE_EVIDENCE,
    }:
        feedback = decision.reason
        if (
            decision.action is ReviewAction.RETRIEVE_EVIDENCE
            and decision.required_evidence
        ):
            feedback += (
                " Required evidence: "
                + "; ".join(decision.required_evidence)
            )
        return ReviewGateVerdict(
            allows_execution=False,
            retryable=True,
            escalated=False,
            feedback=feedback,
            decision=decision,
        )

    return ReviewGateVerdict(
        allows_execution=False,
        retryable=False,
        escalated=True,
        feedback=decision.reason,
        decision=decision,
    )
