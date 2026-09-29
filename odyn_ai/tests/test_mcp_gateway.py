import unittest
from unittest.mock import AsyncMock, patch

from odyn_ai.core.mcp_gateway import MCPGateway


class MCPGatewayTests(unittest.IsolatedAsyncioTestCase):
    def test_register_and_list_server(self):
        gateway = MCPGateway()
        server = gateway.register_mcp_server("narzedzia", "http://localhost:9000/mcp")
        self.assertEqual(server.name, "narzedzia")
        self.assertEqual(gateway.list_servers(), [{"name": "narzedzia", "endpoint": "http://localhost:9000/mcp", "protocol_version": None, "tool_count": 0}])

    def test_invalid_endpoint_is_rejected(self):
        gateway = MCPGateway()
        for endpoint in ("not-an-url", "ftp://localhost/mcp", "http://user:pass@localhost/mcp"):
            with self.assertRaises(ValueError):
                gateway.register_mcp_server("narzedzia", endpoint)

    @patch("odyn_ai.core.mcp_gateway.JsonStore")
    def test_registry_can_persist(self, store_cls):
        store = store_cls.return_value
        store.load.return_value = [{"name": "narzedzia", "endpoint": "http://localhost:9000/mcp"}]
        gateway = MCPGateway()
        self.assertEqual(gateway.list_servers()[0]["name"], "narzedzia")
        gateway.unregister_mcp_server("narzedzia")
        store.save.assert_called_once_with([])

    @patch("odyn_ai.core.mcp_gateway.httpx.AsyncClient")
    async def test_initialize_discovers_tools(self, client_cls):
        init_response = type("Response", (), {"json": lambda self: {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18", "capabilities": {}}}, "raise_for_status": lambda self: None})()
        tools_response = type("Response", (), {"json": lambda self: {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "search", "description": "Szukaj", "inputSchema": {"type": "object"}}]}}, "raise_for_status": lambda self: None})()
        client = AsyncMock()
        client.post.side_effect = [init_response, tools_response]
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client_cls.return_value = client
        gateway = MCPGateway()
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
        gateway = MCPGateway()
        gateway.register_mcp_server("narzedzia", "http://localhost:9000/mcp")
        result = await gateway.execute_tool("narzedzia", "search", {"query": "ODYN"})
        self.assertTrue(result["result"]["ok"])
        body = client.post.await_args.kwargs["json"]
        self.assertEqual(body["method"], "tools/call")
        self.assertEqual(body["params"]["name"], "search")

    async def test_unknown_server_is_rejected(self):
        gateway = MCPGateway()
        with self.assertRaises(ValueError):
            await gateway.execute_tool("brak", "search", {})


if __name__ == "__main__":
    unittest.main()
