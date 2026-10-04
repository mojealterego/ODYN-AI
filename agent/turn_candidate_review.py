"""Conversation-loop phase for deterministic candidate review gating.

Runs after provider response normalization and before either final-text handling or
the tool round. A configured reviewer may inspect a deep-copied candidate snapshot;
only ReviewAction.ACCEPT may fall through to the existing Hermes pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from agent.cognition.gate_policy import classify_review_decision
from agent.cognition.review_boundary import evaluate_candidate_review
from agent.turn_failure_copy import stamp_failure
from agent.turn_truncation import partial_result


@dataclass(frozen=True)
class CandidateReviewPhaseVerdict:
    """Outcome of the pre-dispatch candidate review phase."""

    action: str
    result: Optional[Dict[str, Any]] = None


def run_candidate_review(
    agent: Any,
    *,
    assistant_message: Any,
    messages: Any,
    effective_task_id: Any,
    finish_reason: Any,
    api_call_count: int,
    conversation_history: Any,
) -> CandidateReviewPhaseVerdict:
    """Review one normalized candidate before text finalization or tool dispatch.

    With no configured reviewer this is a strict no-op. A reviewer ACCEPT preserves
    the upstream flow. Any other typed action terminates this turn as incomplete,
    before tool validation, persistence of tool-call rows, approvals, or dispatch.
    A later DecisionCycle layer may convert retryable review actions into bounded
    regeneration; this phase establishes the fail-closed execution boundary first.
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

    verdict = classify_review_decision(decision)
    if verdict.allows_execution:
        return CandidateReviewPhaseVerdict("fallthrough")

    agent._cleanup_task_resources(effective_task_id)
    agent._persist_session(messages, conversation_history)

    result = partial_result(
        messages,
        api_call_count,
        "",
        error=verdict.feedback,
    )
    result.update(
        review_action=decision.action.value,
        review_confidence=decision.confidence,
        review_feedback=verdict.feedback,
        turn_exit_reason="candidate_review_blocked",
    )
    return CandidateReviewPhaseVerdict(
        "return",
        stamp_failure(result, "loop_error", verdict.retryable),
    )
