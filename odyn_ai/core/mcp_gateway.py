from __future__ import annotations

from dataclasses import dataclass, field
import asyncio
import base64
import itertools
import json
import os
import time
from collections import deque
from urllib.parse import urlparse

import httpx

from odyn_ai.core.mcp_oauth import OAuthAuthorizationClient
from odyn_ai.core.sandbox import SandboxRunner
from odyn_ai.core.secret_manager import NativeSecretManager
from odyn_ai.core.ssrf import SSRFPolicy

from odyn_ai.core.state import JsonStore


@dataclass
class MCPAuth:
    """Reference to credentials kept outside the MCP registry."""

    kind: str = "none"  # none | api_key | bearer | oauth2_client_credentials
    secret_env: str | None = None
    header: str = "Authorization"
    prefix: str = "Bearer "
    client_id_env: str | None = None
    client_secret_env: str | None = None
    token_url: str | None = None
    scope: str | None = None
    authorization_url: str | None = None
    redirect_uri: str | None = None
    client_id: str | None = None


@dataclass
class MCPServer:
    name: str
    endpoint: str
    protocol_version: str | None = None
    capabilities: dict = field(default_factory=dict)
    tools: list[dict] = field(default_factory=list)
    session_id: str | None = None
    auth: MCPAuth = field(default_factory=MCPAuth)


class SecretStore:
    """Native OS secret store; environment variables are not a production fallback."""

    def __init__(self, prefix: str = "ODYN_SECRET_", native: NativeSecretManager | None = None, allow_env_fallback: bool = False) -> None:
        self.prefix = prefix
        self.native = native
        self.allow_env_fallback = allow_env_fallback

    def get(self, env_name: str | None) -> str | None:
        if not env_name:
            return None
        if not env_name.startswith(self.prefix):
            raise ValueError("Sekret MCP musi wskazywać nazwę ODYN_SECRET_*.")
        key = env_name[len(self.prefix):]
        if self.native is not None:
            return self.native.get(key)
        if self.allow_env_fallback:
            return os.getenv(env_name)
        raise RuntimeError("Brak natywnego Secret Managera; odmowa użycia sekretu ze środowiska.")

    def set_local(self, env_name: str, value: str) -> None:
        if not env_name.startswith(self.prefix):
            raise ValueError("Nazwa sekretu musi zaczynać się od ODYN_SECRET_.")
        if self.native is None:
            raise RuntimeError("Brak natywnego Secret Managera.")
        self.native.set(env_name[len(self.prefix):], value)


class RateLimiter:
    def __init__(self, max_requests: int = 30, window_seconds: float = 60.0) -> None:
        self.max_requests = max(1, max_requests)
        self.window_seconds = max(1.0, window_seconds)
        self._events: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, key: str) -> None:
        async with self._lock:
            now = time.monotonic()
            events = self._events.setdefault(key, deque())
            while events and now - events[0] >= self.window_seconds:
                events.popleft()
            if len(events) >= self.max_requests:
                retry_after = self.window_seconds - (now - events[0])
                raise RuntimeError(f"Limit wywołań MCP przekroczony. Spróbuj ponownie za {retry_after:.1f} s.")
            events.append(now)


class MCPGateway:
    """Hardened MCP gateway with allowlisting, sessions, auth, policy and audit."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        data_dir: str | None = None,
        allowed_hosts: set[str] | None = None,
        tool_policy: dict[str, str] | None = None,
        rate_limit: int = 30,
        rate_window: float = 60.0,
        audit_max_entries: int = 1000,
        ssrf_allow_private: bool = False,
        secret_manager: NativeSecretManager | None = None,
        sandbox: SandboxRunner | None = None,
    ) -> None:
        self.connected_servers: dict[str, MCPServer] = {}
        self.timeout = timeout
        self.allowed_hosts = {h.lower() for h in (allowed_hosts or set())}
        self.tool_policy = tool_policy or {}
        self._request_ids = itertools.count(1)
        self._store = JsonStore("mcp_servers", data_dir)
        self._audit = JsonStore("mcp_audit", data_dir)
        self._audit_max_entries = audit_max_entries
        self._secret_store = SecretStore(native=secret_manager, allow_env_fallback=False)
        self._ssrf = SSRFPolicy(allow_private=ssrf_allow_private)
        self._sandbox = sandbox or SandboxRunner()
        self._rate_limiter = RateLimiter(rate_limit, rate_window)
        self._load_registry()

    def _load_registry(self) -> None:
        for item in self._store.load([]):
            try:
                auth_data = item.get("auth", {})
                auth = MCPAuth(
                    kind=str(auth_data.get("kind", "none")),
                    secret_env=auth_data.get("secret_env"),
                    header=str(auth_data.get("header", "Authorization")),
                    prefix=str(auth_data.get("prefix", "Bearer ")),
                    client_id_env=auth_data.get("client_id_env"),
                    client_secret_env=auth_data.get("client_secret_env"),
                    token_url=auth_data.get("token_url"),
                    scope=auth_data.get("scope"),
                    authorization_url=auth_data.get("authorization_url"),
                    redirect_uri=auth_data.get("redirect_uri"),
                    client_id=auth_data.get("client_id"),
                )
                server = MCPServer(
                    name=str(item["name"]),
                    endpoint=str(item["endpoint"]),
                    protocol_version=item.get("protocol_version"),
                    capabilities=item.get("capabilities", {}),
                    tools=item.get("tools", []),
                    session_id=item.get("session_id"),
                    auth=auth,
                )
                self.connected_servers[server.name] = server
            except (KeyError, TypeError, ValueError):
                continue

    def _persist_registry(self) -> None:
        self._store.save([
            {
                "name": s.name,
                "endpoint": s.endpoint,
                "protocol_version": s.protocol_version,
                "capabilities": s.capabilities,
                "tools": s.tools,
                "session_id": s.session_id,
                "auth": {
                    "kind": s.auth.kind,
                    "secret_env": s.auth.secret_env,
                    "header": s.auth.header,
                    "prefix": s.auth.prefix,
                    "client_id_env": s.auth.client_id_env,
                    "client_secret_env": s.auth.client_secret_env,
                    "token_url": s.auth.token_url,
                    "scope": s.auth.scope,
                    "authorization_url": s.auth.authorization_url,
                    "redirect_uri": s.auth.redirect_uri,
                    "client_id": s.auth.client_id,
                },
            }
            for s in self.connected_servers.values()
        ])

    def _audit_event(self, event: dict) -> None:
        entries = self._audit.load([])
        if not isinstance(entries, list):
            entries = []
        safe = {k: v for k, v in event.items() if k not in {"payload", "arguments", "secret", "token"}}
        entries.append({"timestamp": time.time(), **safe})
        self._audit.save(entries[-self._audit_max_entries:])

    def _validate_endpoint(self, endpoint: str) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Endpoint MCP musi być poprawnym adresem HTTP/HTTPS.")
        if parsed.username or parsed.password:
            raise ValueError("Endpoint MCP nie może zawierać danych uwierzytelniających w URL.")
        host = (parsed.hostname or "").lower()
        if not host or host not in self.allowed_hosts:
            raise PermissionError(f"Host MCP '{host}' nie znajduje się na allowliście.")
        self._ssrf.validate_url(endpoint)

    def register_mcp_server(self, server_name: str, endpoint: str, *, auth: MCPAuth | None = None) -> MCPServer:
        name = server_name.strip()
        url = endpoint.strip()
        if not name:
            raise ValueError("Nazwa serwera MCP nie może być pusta.")
        self._validate_endpoint(url)
        auth = auth or MCPAuth()
        if auth.kind not in {"none", "api_key", "bearer", "oauth2_client_credentials"}:
            raise ValueError("Typ uwierzytelniania MCP musi być: none, api_key albo bearer.")
        if auth.kind == "oauth2_client_credentials" and (not auth.client_id_env or not auth.client_secret_env or not auth.token_url):
            raise ValueError("OAuth2 Client Credentials wymaga client_id_env, client_secret_env i token_url.")
        if auth.kind == "oauth2_authorization_code" and (not auth.authorization_url or not auth.token_url or not auth.client_id or not auth.redirect_uri):
            raise ValueError("OAuth Authorization Code wymaga authorization_url, token_url, client_id i redirect_uri.")
        if auth.kind == "oauth2_client_credentials":
            self._secret_store.get(auth.client_id_env); self._secret_store.get(auth.client_secret_env)
        elif auth.kind in {"api_key", "bearer"}:
            self._secret_store.get(auth.secret_env)
        server = MCPServer(name=name, endpoint=url, auth=auth)
        self.connected_servers[name] = server
        self._persist_registry()
        self._audit_event({"action": "register", "server": name, "endpoint": url, "result": "ok"})
        return server

    def create_oauth_authorization(self, server_name: str):
        server = self.get_server(server_name)
        auth = server.auth
        if auth.kind != "oauth2_authorization_code" or not auth.authorization_url or not auth.token_url or not auth.client_id or not auth.redirect_uri:
            raise ValueError("Serwer MCP nie ma kompletnej konfiguracji OAuth Authorization Code + PKCE.")
        client = OAuthAuthorizationClient(
            authorization_endpoint=auth.authorization_url,
            token_endpoint=auth.token_url,
            client_id=auth.client_id,
            redirect_uri=auth.redirect_uri,
            scope=auth.scope or "",
        )
        server._oauth_client = client
        return client.create_authorization_request()

    async def complete_oauth_authorization(self, server_name: str, code: str, state: str):
        client = getattr(self.get_server(server_name), "_oauth_client", None)
        if client is None:
            raise PermissionError("Brak oczekującej sesji OAuth PKCE.")
        token = await client.exchange_code(code, state)
        self._audit_event({"action": "oauth_authorization", "server": server_name, "result": "ok"})
        return token

    async def refresh_oauth_authorization(self, server_name: str):
        client = getattr(self.get_server(server_name), "_oauth_client", None)
        if client is None:
            raise PermissionError("Brak sesji OAuth PKCE.")
        token = await client.refresh()
        self._audit_event({"action": "oauth_refresh", "server": server_name, "result": "ok"})
        return token

    def unregister_mcp_server(self, server_name: str) -> bool:
        removed = self.connected_servers.pop(server_name, None) is not None
        if removed:
            self._persist_registry()
            self._audit_event({"action": "unregister", "server": server_name, "result": "ok"})
        return removed

    def list_servers(self) -> list[dict[str, object]]:
        return [
            {
                "name": s.name,
                "endpoint": s.endpoint,
                "protocol_version": s.protocol_version,
                "tool_count": len(s.tools),
                "session": bool(s.session_id),
                "auth": s.auth.kind,
            }
            for s in self.connected_servers.values()
        ]

    def get_server(self, server_name: str) -> MCPServer:
        server = self.connected_servers.get(server_name)
        if server is None:
            raise ValueError(f"Serwer MCP {server_name} nie jest zarejestrowany.")
        return server

    async def _oauth_token(self, server: MCPServer) -> str:
        auth = server.auth
        client_id = self._secret_store.get(auth.client_id_env)
        client_secret = self._secret_store.get(auth.client_secret_env)
        if not client_id or not client_secret or not auth.token_url:
            raise PermissionError("Brak kompletnej konfiguracji OAuth2 Client Credentials.")
        if not hasattr(server, "_oauth_token_value"):
            server._oauth_token_value = None
            server._oauth_token_expiry = 0.0
        if server._oauth_token_value and time.time() < server._oauth_token_expiry - 30:
            return server._oauth_token_value
        self._validate_endpoint(auth.token_url)
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                response = await client.post(
                    auth.token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        **({"scope": auth.scope} if auth.scope else {}),
                    },
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            self._audit_event({"action": "oauth_token", "server": server.name, "result": "error"})
            raise RuntimeError(f"Nie udało się uzyskać tokena OAuth2 dla {server.name}.") from exc
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            raise RuntimeError(f"Serwer OAuth2 dla {server.name} nie zwrócił access_token.")
        server._oauth_token_value = str(token)
        server._oauth_token_expiry = time.time() + float(payload.get("expires_in", 300))
        self._audit_event({"action": "oauth_token", "server": server.name, "result": "ok"})
        return server._oauth_token_value

    async def _headers_async(self, server: MCPServer) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": server.protocol_version or "2025-06-18",
        }
        if server.session_id:
            headers["Mcp-Session-Id"] = server.session_id
        if server.auth.kind == "oauth2_client_credentials":
            headers["Authorization"] = "Bearer " + await self._oauth_token(server)
        else:
            secret = self._secret_store.get(server.auth.secret_env)
            if server.auth.kind != "none" and not secret:
                raise PermissionError(f"Brak sekretu MCP wskazanego przez {server.auth.secret_env}.")
            if secret:
                headers[server.auth.header] = server.auth.prefix + secret if server.auth.kind == "bearer" else secret
        return headers

    def _headers(self, server: MCPServer) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": server.protocol_version or "2025-06-18",
        }
        if server.session_id:
            headers["Mcp-Session-Id"] = server.session_id
        secret = self._secret_store.get(server.auth.secret_env)
        if server.auth.kind != "none" and not secret:
            raise PermissionError(f"Brak sekretu MCP wskazanego przez {server.auth.secret_env}.")
        if secret:
            value = server.auth.prefix + secret if server.auth.kind == "bearer" else secret
            headers[server.auth.header] = value
        return headers

    @staticmethod
    def _parse_sse(text: str) -> dict:
        for block in text.split("\n\n"):
            data_lines = [line[5:].strip() for line in block.splitlines() if line.startswith("data:")]
            if data_lines:
                try:
                    value = json.loads("\n".join(data_lines))
                    if isinstance(value, dict):
                        return value
                except json.JSONDecodeError:
                    continue
        raise ValueError("Serwer MCP zwrócił nieprawidłowy strumień SSE.")

    async def _rpc(self, server: MCPServer, method: str, params: dict | None = None) -> dict:
        await self._rate_limiter.acquire(server.name)
        request_id = next(self._request_ids)
        body = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            body["params"] = params
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                response = await client.post(server.endpoint, json=body, headers=await self._headers_async(server))
                response.raise_for_status()
                response_headers = getattr(response, "headers", {}) or {}
                session_id = response_headers.get("Mcp-Session-Id")
                if session_id:
                    server.session_id = session_id
                    self._persist_registry()
                content_type = response_headers.get("content-type", "")
                data = self._parse_sse(response.text) if "text/event-stream" in content_type else response.json()
        except httpx.TimeoutException as exc:
            self._audit_event({"action": "rpc", "server": server.name, "method": method, "result": "timeout"})
            raise TimeoutError(f"Serwer MCP {server.name} przekroczył limit czasu.") from exc
        except httpx.HTTPError as exc:
            self._audit_event({"action": "rpc", "server": server.name, "method": method, "result": "http_error"})
            raise RuntimeError(f"Błąd połączenia z serwerem MCP {server.name}: {exc}") from exc
        except ValueError as exc:
            self._audit_event({"action": "rpc", "server": server.name, "method": method, "result": "invalid_response"})
            raise ValueError(f"Serwer MCP {server.name} zwrócił nieprawidłową odpowiedź.") from exc
        if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
            raise ValueError("Serwer MCP zwrócił nieprawidłową odpowiedź JSON-RPC.")
        if "error" in data:
            error = data["error"]
            message = error.get("message", "Nieznany błąd MCP") if isinstance(error, dict) else str(error)
            self._audit_event({"action": "rpc", "server": server.name, "method": method, "result": "mcp_error"})
            raise RuntimeError(f"MCP {method}: {message}")
        self._audit_event({"action": "rpc", "server": server.name, "method": method, "result": "ok"})
        return data

    async def initialize(self, server_name: str) -> dict:
        server = self.get_server(server_name)
        result = await self._rpc(server, "initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "clientInfo": {"name": "ODYN AI", "version": "0.1.0"},
        })
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

    def _authorize_tool(self, server: MCPServer, tool_name: str) -> None:
        rule = self.tool_policy.get(f"{server.name}:{tool_name}", self.tool_policy.get(tool_name, "deny"))
        if rule == "deny":
            raise PermissionError(f"Narzędzie MCP '{tool_name}' jest zablokowane przez politykę ODYN.")
        if rule not in {"allow", "high_risk"}:
            raise PermissionError(f"Nieznana reguła uprawnień dla narzędzia '{tool_name}'.")
        if rule == "high_risk":
            raise PermissionError(f"Narzędzie MCP '{tool_name}' wymaga jawnego zatwierdzenia operacji wysokiego ryzyka.")

    async def execute_tool(self, server_name: str, tool_name: str, payload: dict) -> dict:
        server = self.get_server(server_name)
        if not tool_name.strip():
            raise ValueError("Nazwa narzędzia MCP nie może być pusta.")
        if not isinstance(payload, dict):
            raise ValueError("Argumenty narzędzia MCP muszą być obiektem JSON.")
        self._authorize_tool(server, tool_name)
        if not server.protocol_version:
            await self.initialize(server_name)
        result = await self._rpc(server, "tools/call", {"name": tool_name, "arguments": payload})
        self._audit_event({"action": "tool_call", "server": server.name, "tool": tool_name, "result": "ok"})
        return result
