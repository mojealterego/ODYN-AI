"""Opt-in enforcement hooks fail closed without changing observer hooks."""

import json
from copy import deepcopy
from unittest.mock import Mock

import pytest

from hermes_cli import plugins


@pytest.fixture
def policy_context(monkeypatch):
    manager = plugins.PluginManager()
    monkeypatch.setattr(plugins, "get_plugin_manager", lambda: manager)
    plugins.clear_thread_tool_whitelist()
    context = plugins.PluginContext(plugins.PluginManifest(name="test-policy"), manager)
    yield context, manager
    plugins.clear_thread_tool_whitelist()


@pytest.mark.parametrize("decision", [None, True, False, "allow", {},
    {"action": "ALLOW"}, {"action": "accept"}, {"action": "block"},
    {"action": "block", "message": " "}, {"action": "block", "message": 42}])
def test_invalid_policy_decision_blocks(policy_context, decision):
    context, _ = policy_context
    context.register_hook("pre_tool_call", lambda **kw: decision, fail_closed=True)
    assert plugins.get_pre_tool_call_block_message("write_file", {"path": "output.txt"})


def test_policy_exception_blocks_without_exposing_exception_text(policy_context):
    context, _ = policy_context
    def broken_policy(**kw):
        raise RuntimeError("private-credential-value")
    context.register_hook("pre_tool_call", broken_policy, fail_closed=True)
    message = plugins.get_pre_tool_call_block_message("write_file", {})
    assert message
    assert "private-credential-value" not in message


def test_allow_uses_snapshot_and_other_policy_can_still_block(policy_context):
    context, _ = policy_context
    args = {"data": {"path": "original.txt"}}
    before = deepcopy(args)
    def allow(**kw):
        kw["args"]["data"]["path"] = "changed.txt"
        return {"action": "allow"}
    context.register_hook("pre_tool_call", allow, fail_closed=True)
    assert plugins.get_pre_tool_call_block_message("write_file", args) is None
    assert args == before
    context.register_hook("pre_tool_call", lambda **kw: {"action": "block", "message": "Denied by quota"}, fail_closed=True)
    assert plugins.get_pre_tool_call_block_message("write_file", args) == "Denied by quota"
    assert args == before


def test_observer_exception_remains_non_blocking(policy_context):
    context, manager = policy_context
    observer = Mock(side_effect=RuntimeError("observer offline"))
    context.register_hook("pre_tool_call", observer)
    assert manager._hooks["pre_tool_call"] == [observer]
    assert plugins.get_pre_tool_call_block_message("read_file", {}) is None
    observer.assert_called_once()


def test_unavailable_snapshot_blocks_before_policy_is_called(policy_context):
    context, _ = policy_context
    class CannotCopy:
        def __deepcopy__(self, memo):
            raise ValueError("Cannot freeze input")
    callback = Mock(return_value={"action": "allow"})
    context.register_hook("pre_tool_call", callback, fail_closed=True)
    assert plugins.get_pre_tool_call_block_message("write_file", {"value": CannotCopy()})
    callback.assert_not_called()


def test_allow_cannot_override_thread_whitelist(policy_context):
    context, _ = policy_context
    callback = Mock(return_value={"action": "allow"})
    context.register_hook("pre_tool_call", callback, fail_closed=True)
    plugins.set_thread_tool_whitelist({"read_file"})
    assert plugins.get_pre_tool_call_block_message("write_file", {})
    callback.assert_not_called()


@pytest.mark.parametrize("flag", ["false", "true", 0, 1, None])
def test_policy_flag_requires_boolean(policy_context, flag):
    context, manager = policy_context
    with pytest.raises(TypeError):
        context.register_hook("pre_tool_call", lambda **kw: None, fail_closed=flag)
    assert not manager._hooks


def test_policy_requires_synchronous_pre_tool_hook(policy_context):
    context, manager = policy_context
    with pytest.raises(ValueError):
        context.register_hook("post_tool_call", lambda **kw: None, fail_closed=True)
    async def async_policy(**kw):
        return {"action": "allow"}
    with pytest.raises(ValueError):
        context.register_hook("pre_tool_call", async_policy, fail_closed=True)
    assert not manager._hooks


@pytest.mark.parametrize("decision,allowed", [({"action": "allow"}, True),
    ({"action": "block", "message": "Denied"}, False), (None, False), ("raise", False)])
def test_real_dispatch_respects_policy(policy_context, monkeypatch, decision, allowed):
    """Exercise the existing public dispatcher and real tool registry."""
    import model_tools
    from tools.registry import ToolRegistry
    context, _ = policy_context
    handler = Mock(return_value='{"success":true}')
    registry = ToolRegistry()
    registry.register(name="policy_probe", toolset="test", schema={
        "name": "policy_probe", "parameters": {"type": "object", "properties": {}}}, handler=handler)
    monkeypatch.setattr(model_tools, "registry", registry)
    def policy(**kw):
        if decision == "raise":
            raise RuntimeError("Policy service unavailable")
        return decision
    context.register_hook("pre_tool_call", policy, fail_closed=True)
    result = json.loads(model_tools.handle_function_call("policy_probe", {}))
    assert handler.call_count == int(allowed)
    assert ("error" not in result) is allowed
