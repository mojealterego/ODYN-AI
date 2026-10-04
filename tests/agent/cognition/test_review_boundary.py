"""Characterization tests for the neutral candidate-review boundary."""

from types import SimpleNamespace

import pytest

from agent.cognition.contracts import ReviewAction, ReviewDecision
from agent.cognition.review_boundary import evaluate_candidate_review


class FakeReviewer:
    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    def review(self, candidate, *, context):
        self.calls.append((candidate, context))
        return self.decision


def test_reviewer_receives_actual_candidate_and_context_snapshot():
    decision = ReviewDecision(
        action=ReviewAction.ACCEPT,
        confidence=0.93,
        reason="accepted",
    )
    reviewer = FakeReviewer(decision)
    agent = SimpleNamespace(_candidate_reviewer=reviewer, session_id="session-1")
    call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="read_file",
            arguments='{"path":"README.md"}',
        ),
    )
    assistant = SimpleNamespace(
        content="I will inspect the README.",
        tool_calls=[call],
    )
    messages = [{"role": "user", "content": "Inspect the project"}]

    result = evaluate_candidate_review(
        agent,
        assistant,
        messages,
        task_id="task-1",
        finish_reason="tool_calls",
    )

    assert result is decision
    assert agent._last_candidate_review_decision is decision
    candidate, context = reviewer.calls[0]
    assert candidate.content == "I will inspect the README."
    assert candidate.tool_calls[0]["name"] == "read_file"
    assert candidate.tool_calls[0]["arguments"] == '{"path":"README.md"}'
    assert candidate.finish_reason == "tool_calls"
    assert context.task_id == "task-1"
    assert context.session_id == "session-1"
    assert context.messages[0]["content"] == "Inspect the project"


def test_missing_reviewer_preserves_existing_flow():
    agent = SimpleNamespace(session_id="session-2")
    assistant = SimpleNamespace(content="answer", tool_calls=[])

    result = evaluate_candidate_review(
        agent,
        assistant,
        [],
        task_id=None,
        finish_reason="stop",
    )

    assert result is None
    assert not hasattr(agent, "_last_candidate_review_decision")


def test_invalid_reviewer_contract_fails_explicitly():
    agent = SimpleNamespace(_candidate_reviewer=object(), session_id=None)
    assistant = SimpleNamespace(content="answer", tool_calls=[])

    with pytest.raises(TypeError, match="review"):
        evaluate_candidate_review(
            agent,
            assistant,
            [],
            task_id=None,
            finish_reason="stop",
        )


def test_configured_reviewer_must_return_review_decision():
    agent = SimpleNamespace(_candidate_reviewer=FakeReviewer(None))
    assistant = SimpleNamespace(content="answer", tool_calls=[])

    with pytest.raises(ValueError, match="ReviewDecision"):
        evaluate_candidate_review(
            agent,
            assistant,
            [],
            task_id=None,
            finish_reason="stop",
        )


def test_reviewer_cannot_mutate_live_history_or_tool_arguments():
    class MutatingReviewer:
        def review(self, candidate, *, context):
            context.messages[0]["content"] = "altered"
            candidate.tool_calls[0]["arguments"]["path"] = "altered"
            return ReviewDecision(
                action=ReviewAction.ACCEPT,
                confidence=1.0,
                reason="accepted",
            )

    messages = [{"role": "user", "content": "original"}]
    arguments = {"path": "original"}
    call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="read_file", arguments=arguments),
    )
    assistant = SimpleNamespace(content="answer", tool_calls=[call])
    agent = SimpleNamespace(_candidate_reviewer=MutatingReviewer())

    evaluate_candidate_review(
        agent,
        assistant,
        messages,
        task_id="task-1",
        finish_reason="tool_calls",
    )

    assert messages[0]["content"] == "original"
    assert call.function.arguments["path"] == "original"
