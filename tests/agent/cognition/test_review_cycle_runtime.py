"""Bounded candidate-review cycle integration tests."""

import json
import uuid
from collections import deque
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent.cognition import ReviewAction, ReviewDecision
from run_agent import AIAgent


def _tool_defs(*names: str) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": f"{name} tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for name in names
    ]


def _tool_call(name="web_search", arguments="{}", call_id=None):
    return SimpleNamespace(
        id=call_id or f"call_{uuid.uuid4().hex[:8]}",
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _response(content="Hello", finish_reason="stop", tool_calls=None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=msg, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], model="test/model", usage=None)


def _agent(*tool_names: str, max_iterations: int = 8) -> AIAgent:
    with (
        patch("model_tools.get_tool_definitions", return_value=_tool_defs(*tool_names)),
        patch("model_tools.check_toolset_requirements", return_value={}),
        patch("hermes_cli.config.load_config", return_value={}),
        patch("hermes_cli.config.load_config_readonly", return_value={}),
        patch("agent.process_bootstrap.OpenAI"),
    ):
        agent = AIAgent(
            api_key="test-key-1234567890",
            base_url="https://openrouter.ai/api/v1",
            max_iterations=max_iterations,
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
        )
    agent.client = MagicMock()
    agent._cached_system_prompt = "You are helpful."
    agent._use_prompt_caching = False
    agent.compression_enabled = False
    agent.save_trajectories = False
    return agent


class SequencedReviewer:
    def __init__(self, *actions: ReviewAction):
        self.actions = deque(actions)
        self.calls = []

    def review(self, candidate, *, context):
        self.calls.append((candidate, context))
        action = self.actions.popleft() if self.actions else ReviewAction.ACCEPT
        return ReviewDecision(
            action=action,
            confidence=0.9,
            reason=f"{action.value} by test reviewer",
            corrections=("revise candidate",) if action is ReviewAction.CORRECT else (),
            required_evidence=("fresh source",) if action is ReviewAction.RETRIEVE_EVIDENCE else (),
        )


@pytest.mark.parametrize(
    "first_action",
    [ReviewAction.CORRECT, ReviewAction.RETRY, ReviewAction.RETRIEVE_EVIDENCE],
)
def test_retryable_review_regenerates_before_dispatch(first_action: ReviewAction):
    agent = _agent("web_search")
    agent.candidate_review_max_attempts = 3
    agent.candidate_review_max_corrections = 2
    agent._candidate_reviewer = SequencedReviewer(
        first_action,
        ReviewAction.ACCEPT,
        ReviewAction.ACCEPT,
    )
    agent.client.chat.completions.create.side_effect = [
        _response(
            content="",
            finish_reason="tool_calls",
            tool_calls=[_tool_call("web_search", '{"query":"first"}', "call-first")],
        ),
        _response(
            content="",
            finish_reason="tool_calls",
            tool_calls=[_tool_call("web_search", '{"query":"revised"}', "call-revised")],
        ),
        _response(content="done", finish_reason="stop", tool_calls=None),
    ]

    with (
        patch("model_tools.handle_function_call", return_value=json.dumps({"ok": True})) as dispatch,
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        result = agent.run_conversation("search")

    dispatch.assert_called_once()
    assert agent.client.chat.completions.create.call_count == 3
    assert result["final_response"] == "done"


def test_review_attempt_limit_blocks_dispatch_after_exhaustion():
    agent = _agent("web_search")
    agent.candidate_review_max_attempts = 2
    agent._candidate_reviewer = SequencedReviewer(
        ReviewAction.RETRY,
        ReviewAction.RETRY,
        ReviewAction.ACCEPT,
    )
    agent.client.chat.completions.create.return_value = _response(
        content="",
        finish_reason="tool_calls",
        tool_calls=[_tool_call("web_search", '{"query":"never"}', "call-never")],
    )

    with (
        patch("model_tools.handle_function_call", return_value="SHOULD_NOT_RUN") as dispatch,
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        result = agent.run_conversation("search")

    dispatch.assert_not_called()
    assert agent.client.chat.completions.create.call_count == 2
    assert result["completed"] is False
    assert result["partial"] is True
    assert result["turn_exit_reason"] == "candidate_review_exhausted"
    assert result["failure_retryable"] is False


def test_correction_budget_blocks_dispatch_after_exhaustion():
    agent = _agent("web_search")
    agent.candidate_review_max_attempts = 4
    agent.candidate_review_max_corrections = 1
    agent._candidate_reviewer = SequencedReviewer(
        ReviewAction.CORRECT,
        ReviewAction.CORRECT,
        ReviewAction.ACCEPT,
    )
    agent.client.chat.completions.create.return_value = _response(
        content="",
        finish_reason="tool_calls",
        tool_calls=[_tool_call("web_search", '{"query":"never"}', "call-never")],
    )

    with (
        patch("model_tools.handle_function_call", return_value="SHOULD_NOT_RUN") as dispatch,
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        result = agent.run_conversation("search")

    dispatch.assert_not_called()
    assert agent.client.chat.completions.create.call_count == 2
    assert result["turn_exit_reason"] == "candidate_review_exhausted"
    assert result["review_action"] == ReviewAction.CORRECT.value
    assert result["failure_retryable"] is False


def test_escalate_remains_terminal_and_never_dispatches():
    agent = _agent("web_search")
    agent._candidate_reviewer = SequencedReviewer(ReviewAction.ESCALATE)
    agent.client.chat.completions.create.return_value = _response(
        content="",
        finish_reason="tool_calls",
        tool_calls=[_tool_call("web_search", '{"query":"blocked"}', "call-blocked")],
    )

    with (
        patch("model_tools.handle_function_call", return_value="SHOULD_NOT_RUN") as dispatch,
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        result = agent.run_conversation("search")

    dispatch.assert_not_called()
    assert agent.client.chat.completions.create.call_count == 1
    assert result["turn_exit_reason"] == "candidate_review_blocked"
    assert result["review_action"] == ReviewAction.ESCALATE.value
