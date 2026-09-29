import unittest
from unittest.mock import AsyncMock, patch

from odyn_ai.core.mcp_gateway import MCPGateway


class MCPGatewayTests(unittest.IsolatedAsyncioTestCase):
    def test_register_and_list_server(self):
        gateway = MCPGateway()
        server = gateway.register_mcp_server("narzedzia", "http://localhost:9000/mcp")

        self.assertEqual(server.name, "narzedzia")
        self.assertEqual(gateway.list_servers(), [
            {"name": "narzedzia", "endpoint": "http://localhost:9000/mcp"}
        ])

    def test_invalid_endpoint_is_rejected(self):
        gateway = MCPGateway()
        with self.assertRaises(ValueError):
            gateway.register_mcp_server("narzedzia", "not-an-url")

    @patch("odyn_ai.core.mcp_gateway.httpx.AsyncClient")
    async def test_execute_tool_delegates_json_rpc_call(self, client_cls):
        response = type("Response", (), {
            "json": lambda self: {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}},
            "raise_for_status": lambda self: None,
        })()
        client = type("Client", (), {})()
        client.post = AsyncMock(return_value=response)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client_cls.return_value = client

        gateway = MCPGateway()
        gateway.register_mcp_server("narzedzia", "http://localhost:9000/mcp")
        result = await gateway.execute_tool("narzedzia", "search", {"query": "ODYN"})

        self.assertTrue(result["result"]["ok"])
        client.post.assert_awaited_once()
        kwargs = client.post.await_args.kwargs
        self.assertEqual(kwargs["json"]["method"], "tools/call")
        self.assertEqual(kwargs["json"]["params"]["name"], "search")

    async def test_unknown_server_is_rejected(self):
        gateway = MCPGateway()
        with self.assertRaises(ValueError):
            await gateway.execute_tool("brak", "search", {})


if __name__ == "__main__":
    unittest.main()
