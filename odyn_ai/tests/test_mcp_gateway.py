import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from odyn_ai.core.mcp_gateway import MCPGateway
from odyn_ai.core.secret_manager import NativeSecretManager


class MCPGatewayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = __import__("unittest").mock.patch.dict(os.environ, {"ODYN_DATA_DIR": self.tmp.name}, clear=False)
        self.env.start()
        class TestKeyring:
            def get_password(self, service, name):
                return os.getenv("ODYN_SECRET_" + name)
            def set_password(self, service, name, value):
                return None
            def delete_password(self, service, name):
                return None
        self.keyring = NativeSecretManager(backend=TestKeyring())

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()
    def test_register_and_list_server(self):
        gateway = MCPGateway(allowed_hosts={"localhost"}, secret_manager=self.keyring, ssrf_allow_private=True)
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
        gateway.get_server("oauth").protocol_version = "2025-06-18"
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
        gateway = MCPGateway(allowed_hosts={"example.com"}, secret_manager=self.keyring)
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
        gateway = MCPGateway(allowed_hosts={"localhost"}, secret_manager=self.keyring, ssrf_allow_private=True)
        with self.assertRaises(ValueError):
            await gateway.execute_tool("brak", "search", {})


if __name__ == "__main__":
    unittest.main()


class SecurityBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_pkce_authorization_request_contains_state_and_challenge(self):
        from odyn_ai.core.mcp_oauth import OAuthAuthorizationClient
        client = OAuthAuthorizationClient(
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            client_id="odyn",
            redirect_uri="http://127.0.0.1:8765/callback",
            scope="mcp",
        )
        request = client.create_authorization_request()
        self.assertTrue(request.state)
        self.assertTrue(request.code_verifier)
        self.assertIn("code_challenge=", request.url)
        self.assertIn("code_challenge_method=S256", request.url)
        self.assertNotIn(request.code_verifier, request.url)

    async def test_pkce_callback_exchanges_code_and_refreshes_token(self):
        from odyn_ai.core.mcp_oauth import OAuthAuthorizationClient
        client = OAuthAuthorizationClient(
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            client_id="odyn",
            redirect_uri="http://127.0.0.1:8765/callback",
        )
        request = client.create_authorization_request()
        response = type("Response", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"access_token": "access-1", "refresh_token": "refresh-1", "expires_in": 300},
        })()
        http = AsyncMock()
        http.post.return_value = response
        http.__aenter__.return_value = http
        http.__aexit__.return_value = None
        with patch("odyn_ai.core.mcp_oauth.httpx.AsyncClient", return_value=http):
            token = await client.exchange_code("auth-code", request.state)
        self.assertEqual(token.access_token, "access-1")
        self.assertEqual(token.refresh_token, "refresh-1")
        self.assertEqual(http.post.await_args.kwargs["data"]["code_verifier"], request.code_verifier)

    def test_ssrf_rejects_private_and_loopback_addresses(self):
        from odyn_ai.core.ssrf import SSRFPolicy
        import ipaddress
        policy = SSRFPolicy()
        with self.assertRaises(PermissionError):
            policy.validate_addresses([ipaddress.ip_address("127.0.0.1")])
        with self.assertRaises(PermissionError):
            policy.validate_addresses([ipaddress.ip_address("169.254.169.254")])

    def test_ssrf_allows_public_address(self):
        from odyn_ai.core.ssrf import SSRFPolicy
        import ipaddress
        SSRFPolicy().validate_addresses([ipaddress.ip_address("1.1.1.1")])

    def test_native_secret_manager_does_not_fallback_to_plaintext(self):
        from odyn_ai.core.secret_manager import NativeSecretManager
        manager = NativeSecretManager(backend=type("Backend", (), {"get": lambda self, k: None, "set": lambda self, k, v: None})())
        with self.assertRaises(RuntimeError):
            manager.require("missing")

    def test_gateway_routes_high_risk_local_tool_to_sandbox(self):
        from odyn_ai.core.sandbox import SandboxRunner
        gateway = MCPGateway(
            allowed_hosts={"localhost"},
            secret_manager=self.keyring,
            ssrf_allow_private=True,
            sandbox=SandboxRunner(backend="unavailable"),
        )
        with self.assertRaises(PermissionError):
            gateway.execute_high_risk_local(["python", "-c", "print(1)"])

    def test_gateway_builds_oauth_pkce_request(self):
        from odyn_ai.core.mcp_gateway import MCPAuth
        gateway = MCPGateway(allowed_hosts={"localhost"}, secret_manager=self.keyring, ssrf_allow_private=True)
        gateway.register_mcp_server(
            "oauth-pkce",
            "http://localhost:9000/mcp",
            auth=MCPAuth(
                kind="oauth2_authorization_code",
                authorization_url="https://auth.example.com/authorize",
                token_url="https://auth.example.com/token",
                client_id="odyn",
                redirect_uri="http://127.0.0.1/callback",
            ),
        )
        request = gateway.create_oauth_authorization("oauth-pkce")
        self.assertIn("code_challenge_method=S256", request.url)

    def test_high_risk_requires_real_sandbox_backend(self):
        from odyn_ai.core.sandbox import SandboxRunner
        runner = SandboxRunner(backend="unavailable")
        with self.assertRaises(PermissionError):
            runner.require_available()
