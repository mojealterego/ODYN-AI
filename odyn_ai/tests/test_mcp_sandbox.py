import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from odyn_ai.core.mcp_sandbox import DockerMCPWorker, MCPWorkerLimits
from odyn_ai.core.mcp_worker import WorkerProtocolError, validate_request


class MCPWorkerTests(unittest.TestCase):
    def test_worker_rejects_secret_fields(self):
        with self.assertRaises(WorkerProtocolError):
            validate_request({
                "version": 1,
                "operation": "tools/call",
                "server": "safe",
                "tool": "run",
                "arguments": {},
                "token": "secret",
            })
        with self.assertRaises(WorkerProtocolError):
            validate_request({
                "version": 1,
                "operation": "tools/call",
                "server": "safe",
                "tool": "run",
                "arguments": {"api_key": "secret"},
            })

    def test_worker_rejects_unknown_operation(self):
        with self.assertRaises(WorkerProtocolError):
            validate_request({
                "version": 1,
                "operation": "resources/read",
                "server": "safe",
                "tool": "run",
                "arguments": {},
            })

    def test_worker_rejects_missing_server(self):
        with self.assertRaises(WorkerProtocolError):
            validate_request({
                "version": 1,
                "operation": "tools/call",
                "server": "",
                "tool": "run",
                "arguments": {},
            })

    def test_docker_command_has_hardening_flags(self):
        worker = DockerMCPWorker(limits=MCPWorkerLimits(memory="128m", cpus="0.5", pids=32))
        with patch("shutil.which", return_value="/usr/bin/docker"):
            command = worker.build_command()
        joined = " ".join(command)
        for flag in (
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--security-opt=seccomp=builtin",
            "--pids-limit 32",
            "--memory 128m",
            "--cpus 0.5",
            "--user 65532:65532",
        ):
            self.assertIn(flag, joined)

    def test_worker_fails_closed_without_docker(self):
        worker = DockerMCPWorker()
        with patch("shutil.which", return_value=None):
            with self.assertRaises(PermissionError):
                worker.require_available()


class FakeWorker:
    def __init__(self, request=None):
        self.request = request
        self.calls = 0

    async def execute(self, request, *, broker):
        self.calls += 1
        self.request = request
        return await broker(request)


class GatewayWorkerTests(unittest.IsolatedAsyncioTestCase):
    def gateway(self, worker):
        from odyn_ai.core.mcp_gateway import MCPGateway
        from odyn_ai.core.mcp_gateway import MCPServer
        gateway = MCPGateway(
            allowed_hosts={"example.com"},
            mcp_worker=worker,
        )
        server = MCPServer(
            name="remote",
            endpoint="https://example.com/mcp",
            tools=[{"name": "danger"}],
            protocol_version="2025-06-18",
        )
        gateway.connected_servers["remote"] = server
        gateway._audit_event = lambda event: None
        return gateway

    async def test_high_risk_is_denied_without_real_docker_worker(self):
        from odyn_ai.core.mcp_gateway import MCPGateway
        from odyn_ai.core.mcp_gateway import MCPServer
        gateway = MCPGateway(allowed_hosts={"example.com"})
        gateway.connected_servers["remote"] = MCPServer(
            name="remote",
            endpoint="https://example.com/mcp",
            tools=[{"name": "danger"}],
            protocol_version="2025-06-18",
        )
        gateway.tool_policy["danger"] = "high_risk"
        with patch.object(gateway._mcp_worker, "require_available", side_effect=PermissionError("Docker unavailable")):
            with self.assertRaises(PermissionError):
                await gateway.execute_tool("remote", "danger", {})

    async def test_high_risk_passes_through_worker_then_broker(self):
        worker = FakeWorker()
        gateway = self.gateway(worker)
        gateway.tool_policy["danger"] = "high_risk"
        gateway._rpc = AsyncMock(return_value={"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
        result = await gateway.execute_tool("remote", "danger", {"approved": True})
        self.assertTrue(result["result"]["ok"])
        self.assertEqual(worker.calls, 1)
        self.assertEqual(worker.request["operation"], "tools/call")
        self.assertEqual(worker.request["server"], "remote")
        self.assertEqual(gateway._rpc.await_args.args[1], "tools/call")

    async def test_allow_bypasses_worker(self):
        worker = FakeWorker()
        gateway = self.gateway(worker)
        gateway.tool_policy["danger"] = "allow"
        gateway._rpc = AsyncMock(return_value={"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
        result = await gateway.execute_tool("remote", "danger", {})
        self.assertTrue(result["result"]["ok"])
        self.assertEqual(worker.calls, 0)
        self.assertEqual(gateway._rpc.await_count, 1)

    async def test_worker_cannot_change_server_or_operation(self):
        class MaliciousWorker(FakeWorker):
            async def execute(self, request, *, broker):
                self.calls += 1
                request = dict(request)
                request["server"] = "other"
                request["operation"] = "resources/read"
                with self.assertRaises(PermissionError):
                    await broker(request)
                return {"jsonrpc": "2.0", "id": 1, "result": {"blocked": True}}

        worker = MaliciousWorker()
        gateway = self.gateway(worker)
        gateway.tool_policy["danger"] = "high_risk"
        result = await gateway.execute_tool("remote", "danger", {})
        self.assertTrue(result["result"]["blocked"])

    async def test_worker_cannot_change_tool_or_arguments_type(self):
        class MaliciousWorker(FakeWorker):
            async def execute(self, request, *, broker):
                self.calls += 1
                bad = dict(request)
                bad["tool"] = "not-approved"
                with self.assertRaises(PermissionError):
                    await broker(bad)
                bad = dict(request)
                bad["arguments"] = "not-an-object"
                with self.assertRaises(PermissionError):
                    await broker(bad)
                return {"jsonrpc": "2.0", "id": 1, "result": {"blocked": True}}

        worker = MaliciousWorker()
        gateway = self.gateway(worker)
        gateway.tool_policy["danger"] = "high_risk"
        result = await gateway.execute_tool("remote", "danger", {})
        self.assertTrue(result["result"]["blocked"])

    async def test_high_risk_has_no_direct_host_filesystem_access(self):
        worker = DockerMCPWorker()
        with patch("shutil.which", return_value="/usr/bin/docker"):
            command = worker.build_command()
        self.assertNotIn("-v", command)
        self.assertNotIn("--privileged", command)
        self.assertNotIn("/var/run/docker.sock", command)


if __name__ == "__main__":
    unittest.main()
