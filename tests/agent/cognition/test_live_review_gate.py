"""Live conversation-loop integration tests for the candidate review gate."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent.cognition import ReviewAction, ReviewDecision
from run_agent import AIAgent


def _make_tool_defs(*names: str) -> list[dict]:
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


def _mock_tool_call(name="web_search", arguments="{}", call_id=None):
    return SimpleNamespace(
        id=call_id or f"call_{uuid.uuid4().hex[:8]}",
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _mock_response(content="Hello", finish_reason="stop", tool_calls=None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=msg, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], model="test/model", usage=None)


def _make_agent(*tool_names: str, max_iterations: int = 4) -> AIAgent:
    with (
        patch("model_tools.get_tool_definitions", return_value=_make_tool_defs(*tool_names)),
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


class FixedReviewer:
    def __init__(self, action: ReviewAction):
        self.action = action
        self.calls = []

    def review(self, candidate, *, context):
        self.calls.append((candidate, context))
        evidence = ("fresh source",) if self.action is ReviewAction.RETRIEVE_EVIDENCE else ()
        return ReviewDecision(
            action=self.action,
            confidence=0.9,
            reason=f"{self.action.value} by test reviewer",
            required_evidence=evidence,
        )


def test_accept_reaches_existing_tool_pipeline():
    agent = _make_agent("web_search")
    agent._candidate_reviewer = FixedReviewer(ReviewAction.ACCEPT)
    agent.client.chat.completions.create.side_effect = [
        _mock_response(
            content="",
            finish_reason="tool_calls",
            tool_calls=[_mock_tool_call("web_search", '{"query":"hermes"}', "call-1")],
        ),
        _mock_response(content="done", finish_reason="stop", tool_calls=None),
    ]

    with (
        patch("model_tools.handle_function_call", return_value=json.dumps({"ok": True})) as dispatch,
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        result = agent.run_conversation("search")

    dispatch.assert_called_once()
    assert result["final_response"] == "done"
    assert agent._candidate_reviewer.calls


@pytest.mark.parametrize(
    "action",
    [
        ReviewAction.CORRECT,
        ReviewAction.RETRY,
        ReviewAction.RETRIEVE_EVIDENCE,
        ReviewAction.ESCALATE,
    ],
)
def test_non_accept_review_never_reaches_tool_dispatch(action: ReviewAction):
    agent = _make_agent("web_search")
    agent._candidate_reviewer = FixedReviewer(action)
    agent.client.chat.completions.create.return_value = _mock_response(
        content="",
        finish_reason="tool_calls",
        tool_calls=[_mock_tool_call("web_search", '{"query":"blocked"}', "call-blocked")],
    )

    with (
        patch("model_tools.handle_function_call", return_value="SHOULD_NOT_RUN") as dispatch,
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        result = agent.run_conversation("search")

    dispatch.assert_not_called()
    assert result["completed"] is False
    assert result["partial"] is True
    assert result["review_action"] == action.value
    assert result["turn_exit_reason"] == "candidate_review_blocked"
