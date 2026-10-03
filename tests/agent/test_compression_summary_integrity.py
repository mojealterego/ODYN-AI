"""Regressions for empty summaries and complete, redacted handoff input."""

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.context_compressor import ContextCompressor, SUMMARY_PREFIX, LEGACY_SUMMARY_PREFIX


def _compressor(**kwargs):
    with patch("agent.context_compressor.get_model_context_length", return_value=100000):
        compressor = ContextCompressor(model="test/main", quiet_mode=True,
            protect_first_n=1, protect_last_n=1, **kwargs)
    compressor.tail_token_budget = 0
    return compressor


def _response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _conversation():
    return [{"role": "system", "content": "Keep the current task."}] + [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"Durable fact {i}"}
        for i in range(12)]


@pytest.mark.parametrize("content", [None, "", " \n\t ", SUMMARY_PREFIX, LEGACY_SUMMARY_PREFIX])
def test_empty_summary_honors_abort_and_preserves_previous_handoff(content):
    compressor = _compressor(abort_on_summary_failure=True)
    compressor._previous_summary = "Earlier decisions and paths"
    messages = _conversation()
    original = deepcopy(messages)
    with patch("agent.context_compressor.call_llm", return_value=_response(content)):
        compressed = compressor.compress(messages, force=True)
    assert compressed == original
    assert compressor._previous_summary == "Earlier decisions and paths"
    assert compressor._last_compress_aborted is True
    assert compressor._last_summary_dropped_count == 0
    assert compressor._last_summary_error


def test_empty_summary_legacy_mode_reports_loss_instead_of_false_success():
    compressor = _compressor(abort_on_summary_failure=False)
    with patch("agent.context_compressor.call_llm", return_value=_response("")):
        compressor.compress(_conversation(), force=True)
    assert compressor._last_summary_fallback_used is True
    assert compressor._last_summary_dropped_count > 0
    assert compressor._last_summary_error


def test_empty_auxiliary_response_retries_main_model_once():
    compressor = _compressor(abort_on_summary_failure=True, summary_model_override="test/aux")
    with patch("agent.context_compressor.call_llm", side_effect=[_response(""), _response("Preserved facts")]) as llm:
        result = compressor._generate_summary(_conversation())
    assert result.endswith("Preserved facts")
    assert llm.call_count == 2
    assert llm.call_args_list[0].kwargs["model"] == "test/aux"
    assert "model" not in llm.call_args_list[1].kwargs


def test_previous_summary_and_focus_are_redacted_before_auxiliary_call():
    compressor = _compressor()
    secret = "sk-proj-" + "a" * 48
    compressor._previous_summary = f"Keep output/report.txt; API key: {secret}"
    with patch("agent.context_compressor.call_llm", return_value=_response("Safe summary")) as llm:
        compressor._generate_summary(_conversation(), focus_topic=f"Investigate credential {secret}")
    prompt = llm.call_args.kwargs["messages"][0]["content"]
    assert secret not in prompt
    assert "output/report.txt" in prompt
    assert "[REDACTED" in prompt


def test_sdk_tool_arguments_have_same_redacted_detail_as_dict_messages():
    compressor = _compressor()
    secret = "sk-proj-" + "b" * 48
    arguments = json.dumps({"path": "output/report.txt", "api_key": secret})
    function = {"name": "write_file", "arguments": arguments}
    dictionary = {"role": "assistant", "content": None, "tool_calls": [{"function": function}]}
    sdk = {"role": "assistant", "content": None, "tool_calls": [SimpleNamespace(function=SimpleNamespace(**function))]}
    original = deepcopy(dictionary)
    dict_text = compressor._serialize_for_summary([dictionary])
    sdk_text = compressor._serialize_for_summary([sdk])
    assert sdk_text == dict_text
    assert "output/report.txt" in sdk_text
    assert secret not in sdk_text
    assert dictionary == original
