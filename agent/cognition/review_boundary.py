"""Neutral pre-dispatch candidate review boundary.

This boundary snapshots the normalized assistant candidate and surrounding
conversation context before any future cognitive reviewer inspects it.
It does not authorize, persist, rewrite, or execute tool calls.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from .contracts import CandidateSnapshot, ReviewContext, ReviewDecision


def evaluate_candidate_review(
    agent: Any,
    assistant_message: Any,
    messages: Sequence[Mapping[str, Any]],
    *,
    task_id: str | None,
    finish_reason: str | None,
) -> ReviewDecision | None:
    """Review one normalized candidate without authorizing or executing tools."""
    reviewer = getattr(agent, "_candidate_reviewer", None)
    if reviewer is None:
        return None

    review = getattr(reviewer, "review", None)
    if not callable(review):
        raise TypeError(
            "_candidate_reviewer must implement review(candidate, context=...)"
        )

    calls: list[dict[str, Any]] = []
    for tool_call in getattr(assistant_message, "tool_calls", None) or ():
        function = getattr(tool_call, "function", None)
        calls.append(
            {
                "id": getattr(tool_call, "id", None),
                "name": getattr(function, "name", None),
                "arguments": deepcopy(getattr(function, "arguments", None)),
            }
        )

    candidate = CandidateSnapshot(
        content=deepcopy(getattr(assistant_message, "content", None)),
        tool_calls=tuple(calls),
        finish_reason=finish_reason,
    )
    context = ReviewContext(
        task_id=task_id,
        session_id=getattr(agent, "session_id", None),
        messages=tuple(deepcopy(messages)),
    )

    decision = review(candidate, context=context)
    if not isinstance(decision, ReviewDecision):
        raise ValueError(
            "A configured candidate reviewer must return ReviewDecision"
        )

    agent._last_candidate_review_decision = decision
    return decision
