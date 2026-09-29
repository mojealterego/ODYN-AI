from __future__ import annotations

from odyn_ai.core.mcp_gateway import MCPGateway, MCPServer
from odyn_ai.core.state import JsonStore


class PersistentMCPGateway(MCPGateway):
    """MCP gateway whose registered endpoints survive application restarts."""

    def __init__(self, data_dir: str | None = None, *, timeout: float = 30.0) -> None:
        super().__init__(timeout=timeout)
        self._store = JsonStore("mcp_servers", data_dir)
        for item in self._store.load([]):
            if isinstance(item, dict) and item.get("name") and item.get("endpoint"):
                try:
                    super().register_mcp_server(item["name"], item["endpoint"])
                except ValueError:
                    continue

    def _persist(self) -> None:
        self._store.save(self.list_servers())

    def register_mcp_server(self, server_name: str, endpoint: str) -> MCPServer:
        server = super().register_mcp_server(server_name, endpoint)
        self._persist()
        return server

    def unregister_mcp_server(self, server_name: str) -> bool:
        removed = super().unregister_mcp_server(server_name)
        if removed:
            self._persist()
        return removed
