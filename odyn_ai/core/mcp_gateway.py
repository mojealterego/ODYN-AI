from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class MCPServer:
    name: str
    endpoint: str


class MCPGateway:
    """Local gateway for registered MCP-compatible HTTP endpoints."""

    def __init__(self, *, timeout: float = 30.0) -> None:
        self.connected_servers: dict[str, MCPServer] = {}
        self.timeout = timeout

    def register_mcp_server(self, server_name: str, endpoint: str) -> MCPServer:
        """Register an external MCP HTTP endpoint."""
        name = server_name.strip()
        url = endpoint.strip()
        parsed = urlparse(url)

        if not name:
            raise ValueError("Nazwa serwera MCP nie może być pusta.")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Endpoint MCP musi być poprawnym adresem HTTP/HTTPS.")

        server = MCPServer(name=name, endpoint=url)
        self.connected_servers[name] = server
        print(f"🔌 MCP Gateway: Zarejestrowano serwer {name} pod adresem {url}")
        return server

    def unregister_mcp_server(self, server_name: str) -> bool:
        return self.connected_servers.pop(server_name, None) is not None

    def list_servers(self) -> list[dict[str, str]]:
        return [
            {"name": server.name, "endpoint": server.endpoint}
            for server in self.connected_servers.values()
        ]

    async def execute_tool(
        self,
        server_name: str,
        tool_name: str,
        payload: dict,
    ) -> dict:
        """Delegate a JSON-RPC-style MCP tool call to a registered endpoint."""
        server = self.connected_servers.get(server_name)
        if server is None:
            raise ValueError(f"Serwer MCP {server_name} nie jest zarejestrowany.")

        if not tool_name.strip():
            raise ValueError("Nazwa narzędzia MCP nie może być pusta.")

        request_body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": payload,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                server.endpoint,
                json=request_body,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, dict):
            raise ValueError("Serwer MCP zwrócił nieprawidłową odpowiedź JSON.")
        return data
