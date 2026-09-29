from __future__ import annotations

from dataclasses import dataclass, field
import itertools
from urllib.parse import urlparse

import httpx

from odyn_ai.core.state import JsonStore


@dataclass
class MCPServer:
    name: str
    endpoint: str
    protocol_version: str | None = None
    capabilities: dict = field(default_factory=dict)
    tools: list[dict] = field(default_factory=list)


class MCPGateway:
    """Local gateway for registered MCP-compatible HTTP servers."""

    def __init__(self, *, timeout: float = 30.0, data_dir: str | None = None) -> None:
        self.connected_servers: dict[str, MCPServer] = {}
        self.timeout = timeout
        self._request_ids = itertools.count(1)
        self._store = JsonStore("mcp_servers", data_dir)
        self._load_registry()

    def _load_registry(self) -> None:
        for item in self._store.load([]):
            try:
                server = MCPServer(
                    name=str(item["name"]),
                    endpoint=str(item["endpoint"]),
                    protocol_version=item.get("protocol_version"),
                    capabilities=item.get("capabilities", {}),
                    tools=item.get("tools", []),
                )
                self.connected_servers[server.name] = server
            except (KeyError, TypeError, ValueError):
                continue

    def _persist_registry(self) -> None:
        self._store.save([
            {
                "name": server.name,
                "endpoint": server.endpoint,
                "protocol_version": server.protocol_version,
                "capabilities": server.capabilities,
                "tools": server.tools,
            }
            for server in self.connected_servers.values()
        ])

    def register_mcp_server(self, server_name: str, endpoint: str) -> MCPServer:
        name = server_name.strip()
        url = endpoint.strip()
        parsed = urlparse(url)
        if not name:
            raise ValueError("Nazwa serwera MCP nie może być pusta.")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Endpoint MCP musi być poprawnym adresem HTTP/HTTPS.")
        if parsed.username or parsed.password:
            raise ValueError("Endpoint MCP nie może zawierać danych uwierzytelniających w URL.")
        server = MCPServer(name=name, endpoint=url)
        self.connected_servers[name] = server
        self._persist_registry()
        print(f"🔌 MCP Gateway: Zarejestrowano serwer {name} pod adresem {url}")
        return server

    def unregister_mcp_server(self, server_name: str) -> bool:
        removed = self.connected_servers.pop(server_name, None) is not None
        if removed:
            self._persist_registry()
        return removed

    def list_servers(self) -> list[dict[str, object]]:
        return [
            {"name": s.name, "endpoint": s.endpoint, "protocol_version": s.protocol_version, "tool_count": len(s.tools)}
            for s in self.connected_servers.values()
        ]

    def get_server(self, server_name: str) -> MCPServer:
        server = self.connected_servers.get(server_name)
        if server is None:
            raise ValueError(f"Serwer MCP {server_name} nie jest zarejestrowany.")
        return server

    async def _rpc(self, server: MCPServer, method: str, params: dict | None = None) -> dict:
        request_id = next(self._request_ids)
        body = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            body["params"] = params
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    server.endpoint,
                    json=body,
                    headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"Serwer MCP {server.name} przekroczył limit czasu.") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Błąd połączenia z serwerem MCP {server.name}: {exc}") from exc
        except ValueError as exc:
            raise ValueError(f"Serwer MCP {server.name} zwrócił nieprawidłowy JSON.") from exc
        if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
            raise ValueError("Serwer MCP zwrócił nieprawidłową odpowiedź JSON-RPC.")
        if "error" in data:
            error = data["error"]
            message = error.get("message", "Nieznany błąd MCP") if isinstance(error, dict) else str(error)
            raise RuntimeError(f"MCP {method}: {message}")
        return data

    async def initialize(self, server_name: str) -> dict:
        server = self.get_server(server_name)
        result = await self._rpc(
            server,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "ODYN AI", "version": "0.1.0"},
            },
        )
        payload = result.get("result", {})
        if not isinstance(payload, dict):
            raise ValueError("MCP initialize zwrócił nieprawidłowe dane result.")
        server.protocol_version = payload.get("protocolVersion")
        server.capabilities = payload.get("capabilities", {})
        self._persist_registry()
        return payload

    async def discover_tools(self, server_name: str) -> list[dict]:
        server = self.get_server(server_name)
        if not server.protocol_version:
            await self.initialize(server_name)
        result = await self._rpc(server, "tools/list", {})
        tools = result.get("result", {}).get("tools", [])
        if not isinstance(tools, list):
            raise ValueError("MCP tools/list zwrócił nieprawidłową listę narzędzi.")
        server.tools = [tool for tool in tools if isinstance(tool, dict)]
        self._persist_registry()
        return server.tools

    async def execute_tool(self, server_name: str, tool_name: str, payload: dict) -> dict:
        server = self.get_server(server_name)
        if not tool_name.strip():
            raise ValueError("Nazwa narzędzia MCP nie może być pusta.")
        if not isinstance(payload, dict):
            raise ValueError("Argumenty narzędzia MCP muszą być obiektem JSON.")
        if not server.protocol_version:
            await self.initialize(server_name)
        return await self._rpc(server, "tools/call", {"name": tool_name, "arguments": payload})
