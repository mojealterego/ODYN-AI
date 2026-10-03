# Enforcing a plugin policy before tool execution

Policy plugins can opt into the existing native `pre_tool_call` hook:

```python
def register(ctx):
    def policy(tool_name, args, **context):
        if tool_name == "write_file" and args.get("path", "").endswith(".env"):
            return {"action": "block", "message": "Credential file writes are denied"}
        return {"action": "allow"}

    ctx.register_hook("pre_tool_call", policy, fail_closed=True)
```

This example demonstrates the API contract, not a complete filesystem policy.
Path-sensitive policies must resolve paths and account for symlinks and the
tool's actual working directory.

Only an explicit `{"action": "allow"}` permits execution. A block decision must
contain a non-empty string `message`. An exception, missing decision, unknown
action or invalid block message becomes a blocking result. Exception text is
not included in the result sent to the model. Only the plugin identifier and
exception type are logged by the enforcement wrapper.

The synchronous callback receives a deep copy of the tool arguments and
execution identifiers. Changes to that copy cannot rewrite the dispatched
call. Failure to create the copy also blocks. Async policies must expose a
synchronous adapter with bounded I/O timeouts; the hook does not provide a
timeout or a background executor. A coroutine returned unexpectedly is closed
and treated as an invalid decision.

Policies compose with existing blocking hooks, per-thread tool whitelists,
native approvals and cognitive review. An allow result cannot override another
block. The existing public dispatcher and the native agent tool path already
consume the hook result; no separate execution loop is introduced.

Observer plugins can keep `register_hook(name, callback)`. Their callback
exceptions remain non-blocking. `fail_closed` must be an actual boolean and
can only be enabled for a synchronous `pre_tool_call` callback.

Install and enable a policy plugin explicitly through the normal plugin
configuration, then start a new session or restart the gateway. This protects
calls only while the policy has successfully registered. It does not make a
disabled, missing or unloadable plugin mandatory. General plugins currently
remain disabled in the embedded Android runtime; this API does not change that
runtime's capabilities.

Plugins execute as trusted code in the host process. This hook is an
application-level enforcement contract, not an operating-system sandbox.
It does not isolate shell processes, networks or malicious in-process code.
