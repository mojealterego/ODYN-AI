"""Conversation-loop phase for bounded deterministic candidate review.

Runs after provider response normalization and before either final-text handling or
the tool round. A configured reviewer may inspect a deep-copied candidate snapshot;
only ReviewAction.ACCEPT may fall through to the existing Hermes pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from agent.cognition.gate_policy import classify_review_decision
from agent.cognition.review_boundary import evaluate_candidate_review
from agent.cognition.review_cycle import (
    ReviewCycleState,
    advance_review_cycle,
    build_review_feedback,
)
from agent.turn_failure_copy import stamp_failure
from agent.turn_truncation import partial_result


@dataclass(frozen=True)
class CandidateReviewPhaseVerdict:
    """Outcome of the pre-dispatch candidate review phase."""

    action: str
    result: Optional[Dict[str, Any]] = None
    review_cycle: ReviewCycleState = field(default_factory=ReviewCycleState)
    review_feedback: str | None = None


def run_candidate_review(
    agent: Any,
    *,
    assistant_message: Any,
    messages: Any,
    effective_task_id: Any,
    finish_reason: Any,
    api_call_count: int,
    conversation_history: Any,
    review_cycle: ReviewCycleState,
) -> CandidateReviewPhaseVerdict:
    """Review one normalized candidate before text finalization or tool dispatch.

    No reviewer is a strict no-op. ACCEPT preserves the upstream flow. CORRECT,
    RETRY, and RETRIEVE_EVIDENCE regenerate within explicit attempt/correction
    budgets. ESCALATE and exhausted budgets terminate before tool persistence,
    approvals, sandboxing, or dispatch.
    """
    decision = evaluate_candidate_review(
        agent,
        assistant_message,
        messages,
        task_id=effective_task_id,
        finish_reason=finish_reason,
    )
    if decision is None:
        return CandidateReviewPhaseVerdict("fallthrough")

    policy = classify_review_decision(decision)
    outcome = advance_review_cycle(
        review_cycle,
        decision,
        max_attempts=getattr(agent, "candidate_review_max_attempts", 3),
        max_corrections=getattr(agent, "candidate_review_max_corrections", 2),
    )

    if outcome.action == "accept":
        agent._last_candidate_review_cycle = outcome.state
        return CandidateReviewPhaseVerdict("fallthrough")

    if outcome.action == "retry":
        return CandidateReviewPhaseVerdict(
            "continue",
            review_cycle=outcome.state,
            review_feedback=build_review_feedback(decision),
        )

    agent._last_candidate_review_cycle = outcome.state
    agent._cleanup_task_resources(effective_task_id)
    agent._persist_session(messages, conversation_history)

    if outcome.exhausted:
        error = (
            "Candidate review cycle exhausted before execution after "
            f"{outcome.state.attempts} review attempts. Last review: {policy.feedback}"
        )
        turn_exit_reason = "candidate_review_exhausted"
    else:
        error = policy.feedback
        turn_exit_reason = "candidate_review_blocked"

    result = partial_result(
        messages,
        api_call_count,
        "",
        error=error,
    )
    result.update(
        review_action=decision.action.value,
        review_confidence=decision.confidence,
        review_feedback=policy.feedback,
        review_attempts=outcome.state.attempts,
        review_corrections=outcome.state.corrections,
        review_history=[item.action.value for item in outcome.state.history],
        review_exhausted=outcome.exhausted,
        turn_exit_reason=turn_exit_reason,
    )
    return CandidateReviewPhaseVerdict(
        "return",
        stamp_failure(result, "loop_error", False),
    )
