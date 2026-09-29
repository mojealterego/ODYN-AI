import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from odyn_ai.core.mcp_gateway import MCPGateway


class MCPGatewayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = __import__("unittest").mock.patch.dict(os.environ, {"ODYN_DATA_DIR": self.tmp.name}, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()
    def test_register_and_list_server(self):
        gateway = MCPGateway(allowed_hosts={"localhost"})
        server = gateway.register_mcp_server("narzedzia", "http://localhost:9000/mcp")
        self.assertEqual(server.name, "narzedzia")
        self.assertEqual(gateway.list_servers(), [{"name": "narzedzia", "endpoint": "http://localhost:9000/mcp", "protocol_version": None, "tool_count": 0, "session": False, "auth": "none"}])

    def test_invalid_endpoint_is_rejected(self):
        gateway = MCPGateway(allowed_hosts={"localhost"})
        for endpoint in ("not-an-url", "ftp://localhost/mcp", "http://user:pass@localhost/mcp"):
            with self.assertRaises(ValueError):
                gateway.register_mcp_server("narzedzia", endpoint)

    @patch("odyn_ai.core.mcp_gateway.JsonStore")
    def test_registry_can_persist(self, store_cls):
        store = store_cls.return_value
        store.load.return_value = [{"name": "narzedzia", "endpoint": "http://localhost:9000/mcp"}]
        gateway = MCPGateway(allowed_hosts={"localhost"})
        self.assertEqual(gateway.list_servers()[0]["name"], "narzedzia")
        gateway.unregister_mcp_server("narzedzia")
        self.assertEqual(store.save.call_args_list[0].args, ([],))

    @patch("odyn_ai.core.mcp_gateway.httpx.AsyncClient")
    async def test_initialize_discovers_tools(self, client_cls):
        init_response = type("Response", (), {"json": lambda self: {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18", "capabilities": {}}}, "raise_for_status": lambda self: None})()
        tools_response = type("Response", (), {"json": lambda self: {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "search", "description": "Szukaj", "inputSchema": {"type": "object"}}]}}, "raise_for_status": lambda self: None})()
        client = AsyncMock()
        client.post.side_effect = [init_response, tools_response]
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client_cls.return_value = client
        gateway = MCPGateway(allowed_hosts={"localhost"})
        gateway.register_mcp_server("narzedzia", "http://localhost:9000/mcp")
        result = await gateway.discover_tools("narzedzia")
        self.assertEqual(result[0]["name"], "search")
        self.assertEqual(result[0]["inputSchema"]["type"], "object")
        self.assertEqual(client.post.await_count, 2)

    @patch("odyn_ai.core.mcp_gateway.httpx.AsyncClient")
    async def test_execute_tool_delegates_json_rpc_call(self, client_cls):
        response = type("Response", (), {"json": lambda self: {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}, "raise_for_status": lambda self: None})()
        client = AsyncMock()
        client.post.return_value = response
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client_cls.return_value = client
        gateway = MCPGateway(allowed_hosts={"localhost"})
        gateway.register_mcp_server("narzedzia", "http://localhost:9000/mcp")
        gateway.tool_policy["search"] = "allow"
        result = await gateway.execute_tool("narzedzia", "search", {"query": "ODYN"})
        self.assertTrue(result["result"]["ok"])
        body = client.post.await_args.kwargs["json"]
        self.assertEqual(body["method"], "tools/call")
        self.assertEqual(body["params"]["name"], "search")

    def test_secret_is_not_persisted(self):
        import tempfile
        from odyn_ai.core.mcp_gateway import MCPAuth
        with tempfile.TemporaryDirectory() as tmp:
            gateway = MCPGateway(allowed_hosts={"localhost"}, data_dir=tmp)
            gateway.register_mcp_server(
                "secure",
                "https://localhost:9000/mcp",
                auth=MCPAuth(kind="bearer", secret_env="ODYN_SECRET_TEST"),
            )
            stored = gateway._store.load([])
            self.assertNotIn("ODYN_SECRET_TEST_VALUE", str(stored))
            self.assertEqual(stored[0]["auth"]["secret_env"], "ODYN_SECRET_TEST")

    @patch.dict(os.environ, {"ODYN_SECRET_CLIENT_ID": "client", "ODYN_SECRET_CLIENT_SECRET": "secret"})
    @patch("odyn_ai.core.mcp_gateway.httpx.AsyncClient")
    async def test_oauth2_client_credentials_fetches_and_uses_bearer_token(self, client_cls):
        from odyn_ai.core.mcp_gateway import MCPAuth
        token_response = type("Response", (), {
            "headers": {},
            "json": lambda self: {"access_token": "oauth-token", "expires_in": 300},
            "raise_for_status": lambda self: None,
        })()
        mcp_response = type("Response", (), {
            "headers": {},
            "json": lambda self: {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}},
            "raise_for_status": lambda self: None,
        })()
        client = AsyncMock()
        client.post.side_effect = [token_response, mcp_response]
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client_cls.return_value = client
        gateway = MCPGateway(allowed_hosts={"localhost"})
        gateway.register_mcp_server(
            "oauth",
            "http://localhost:9000/mcp",
            auth=MCPAuth(
                kind="oauth2_client_credentials",
                client_id_env="ODYN_SECRET_CLIENT_ID",
                client_secret_env="ODYN_SECRET_CLIENT_SECRET",
                token_url="http://localhost:9000/oauth/token",
            ),
        )
        gateway.tool_policy["search"] = "allow"
        result = await gateway.execute_tool("oauth", "search", {})
        self.assertTrue(result["result"]["ok"])
        calls = client.post.await_args_list
        self.assertEqual(calls[0].kwargs["data"]["grant_type"], "client_credentials")
        self.assertEqual(calls[1].kwargs["headers"]["Authorization"], "Bearer oauth-token")

    def test_missing_secret_fails_closed(self):
        from odyn_ai.core.mcp_gateway import MCPAuth
        gateway = MCPGateway(allowed_hosts={"localhost"})
        gateway.register_mcp_server(
            "secure", "https://localhost:9000/mcp",
            auth=MCPAuth(kind="bearer", secret_env="ODYN_SECRET_DOES_NOT_EXIST"),
        )
        with self.assertRaises(PermissionError):
            gateway._headers(gateway.get_server("secure"))

    def test_non_allowlisted_host_is_rejected(self):
        gateway = MCPGateway(allowed_hosts={"example.com"})
        with self.assertRaises(PermissionError):
            gateway.register_mcp_server("local", "http://localhost:9000/mcp")

    @patch("odyn_ai.core.mcp_gateway.httpx.AsyncClient")
    async def test_streamable_http_sse_response_and_session_are_supported(self, client_cls):
        response = type("Response", (), {
            "headers": {"content-type": "text/event-stream", "Mcp-Session-Id": "session-123"},
            "text": 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n',
            "raise_for_status": lambda self: None,
        })()
        client = AsyncMock()
        client.post.return_value = response
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client_cls.return_value = client
        gateway = MCPGateway(allowed_hosts={"localhost"})
        gateway.register_mcp_server("narzedzia", "http://localhost:9000/mcp")
        gateway.tool_policy["search"] = "allow"
        result = await gateway.execute_tool("narzedzia", "search", {})
        self.assertTrue(result["result"]["ok"])
        self.assertEqual(gateway.get_server("narzedzia").session_id, "session-123")
        self.assertEqual(client.post.await_args.kwargs["headers"]["Mcp-Session-Id"], "session-123")

    async def test_rate_limit_blocks_excess_requests(self):
        gateway = MCPGateway(allowed_hosts={"localhost"}, rate_limit=1, rate_window=60)
        await gateway._rate_limiter.acquire("narzedzia")
        with self.assertRaises(RuntimeError):
            await gateway._rate_limiter.acquire("narzedzia")

    async def test_unknown_server_is_rejected(self):
        gateway = MCPGateway()
        with self.assertRaises(ValueError):
            await gateway.execute_tool("brak", "search", {})


if __name__ == "__main__":
    unittest.main()
