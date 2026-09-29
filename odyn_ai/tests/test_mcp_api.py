import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from odyn_ai.api import server


class MCPApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_register_list_and_remove_mcp_server(self):
        with patch.object(server, "mcp_gateway") as gateway:
            gateway.register_mcp_server.return_value = SimpleNamespace(name="narzedzia", endpoint="http://localhost:9000/mcp")
            gateway.list_servers.return_value = [{"name": "narzedzia", "endpoint": "http://localhost:9000/mcp"}]
            gateway.unregister_mcp_server.return_value = True
            transport = httpx.ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://odyn.test") as client:
                response = await client.post("/api/mcp/servers", json={"name": "narzedzia", "endpoint": "http://localhost:9000/mcp"})
                self.assertEqual(response.status_code, 200)
                response = await client.get("/api/mcp/servers")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["servers"][0]["name"], "narzedzia")
                response = await client.delete("/api/mcp/servers/narzedzia")
                self.assertEqual(response.status_code, 200)

    async def test_execute_tool_maps_gateway_errors(self):
        with patch.object(server, "mcp_gateway") as gateway:
            gateway.execute_tool = AsyncMock(side_effect=RuntimeError("Serwer MCP odmówił wywołania."))
            transport = httpx.ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://odyn.test") as client:
                response = await client.post(
                    "/api/mcp/tools/execute",
                    json={"server_name": "narzedzia", "tool_name": "search", "payload": {"q": "ODYN"}},
                )
            self.assertEqual(response.status_code, 502)
            self.assertIn("odmówił", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
