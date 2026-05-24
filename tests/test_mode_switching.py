"""Tests for MCPClient mode switching: default, auto-fallback, force mock, strict mode."""

import os
import pytest
from unittest.mock import patch, MagicMock

from lifi_agent.mcp_client import MCPClient
from lifi_agent.agent import LifAgent


class TestDefaultMode:
    def test_default_mode_tries_local_mcp(self, monkeypatch):
        """MCPClient starts with _mock_mode=False."""
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        monkeypatch.delenv("LIFI_AGENT_STRICT_MODE", raising=False)
        client = MCPClient()
        assert client._mock_mode is False

    def test_default_is_mock_mode_false(self, monkeypatch):
        """is_mock_mode() returns False when no env var and no fallback."""
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        monkeypatch.delenv("LIFI_AGENT_STRICT_MODE", raising=False)
        client = MCPClient()
        assert client.is_mock_mode() is False


class TestAutoFallback:
    def test_auto_fallback_on_refused(self, monkeypatch):
        """MCPClient with bad port auto-sets _mock_mode=True on connect."""
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        monkeypatch.delenv("LIFI_AGENT_STRICT_MODE", raising=False)
        client = MCPClient(url="http://localhost:1", timeout=2)
        assert client._mock_mode is False
        info = client.connect()
        assert client._mock_mode is True
        assert client._connected is True
        assert "serverInfo" in info

    def test_auto_fallback_is_mock_mode(self, monkeypatch):
        """After auto-fallback, is_mock_mode() returns True."""
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        monkeypatch.delenv("LIFI_AGENT_STRICT_MODE", raising=False)
        client = MCPClient(url="http://localhost:1", timeout=2)
        client.connect()
        assert client.is_mock_mode() is True

    def test_auto_fallback_call_returns_demo_data(self, monkeypatch):
        """After auto-fallback, call() returns demo data."""
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        monkeypatch.delenv("LIFI_AGENT_STRICT_MODE", raising=False)
        client = MCPClient(url="http://localhost:1", timeout=2)
        client.connect()
        result = client.call("get-supported-routes", {})
        assert isinstance(result, list)
        assert len(result) > 0


class TestForceMockMode:
    def test_force_mock_mode(self, monkeypatch):
        """LIFI_AGENT_MOCK_MODE=1 forces mock mode without trying connection."""
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        # is_mock_mode should be true immediately via env var
        assert client.is_mock_mode() is True

    def test_force_mock_connect(self, monkeypatch):
        """LIFI_AGENT_MOCK_MODE=1 connect() returns mock server info."""
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        info = client.connect()
        assert "serverInfo" in info
        assert info["serverInfo"]["name"] == "lifi-intents-demo"
        assert client._mock_mode is True

    def test_force_mock_init_session(self, monkeypatch):
        """LIFI_AGENT_MOCK_MODE=1 _init_session_sync() returns demo-session."""
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        sid = client._init_session_sync()
        assert sid == "demo-session"
        assert client._connected is True

    def test_force_mock_no_http_request(self, monkeypatch):
        """LIFI_AGENT_MOCK_MODE=1 should not make any HTTP requests."""
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        mock_http = MagicMock()
        client._sync_client = mock_http
        client.connect()
        mock_http.post.assert_not_called()


class TestStrictMode:
    def test_strict_mode_blocks_fallback(self, monkeypatch):
        """LIFI_AGENT_STRICT_MODE=1 raises ConnectError on bad port."""
        monkeypatch.setenv("LIFI_AGENT_STRICT_MODE", "1")
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        client = MCPClient(url="http://localhost:1", timeout=2)
        with pytest.raises(Exception) as exc_info:
            client.connect()
        # Should be a ConnectError, not a fallback
        assert client._mock_mode is False

    def test_strict_mode_is_strict(self, monkeypatch):
        """is_strict_mode() returns True when env var is set."""
        monkeypatch.setenv("LIFI_AGENT_STRICT_MODE", "1")
        assert MCPClient.is_strict_mode() is True

    def test_strict_mode_allows_local(self, monkeypatch):
        """LIFI_AGENT_STRICT_MODE=1 with good port works normally."""
        monkeypatch.setenv("LIFI_AGENT_STRICT_MODE", "1")
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        client = MCPClient(url="http://localhost:3333/mcp", timeout=2)
        # Mock a successful HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"mcp-session-id": "test-session"}
        mock_response.text = 'data: {"result": {"serverInfo": {"name": "test", "version": "1.0"}}}\n'

        mock_http = MagicMock()
        mock_http.post.return_value = mock_response
        client._sync_client = mock_http
        info = client.connect()
        assert client._mock_mode is False
        assert client._connected is True
        assert "serverInfo" in info

    def test_strict_mode_conflict_with_mock(self, monkeypatch):
        """LIFI_AGENT_STRICT_MODE=1 + LIFI_AGENT_MOCK_MODE=1 raises RuntimeError."""
        monkeypatch.setenv("LIFI_AGENT_STRICT_MODE", "1")
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        with pytest.raises(RuntimeError, match="conflicts"):
            client.connect()


class TestIsMockModeMethod:
    def test_is_mock_mode_false_by_default(self, monkeypatch):
        """is_mock_mode() is False when nothing is set."""
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        monkeypatch.delenv("LIFI_AGENT_STRICT_MODE", raising=False)
        client = MCPClient()
        assert client.is_mock_mode() is False

    def test_is_mock_mode_via_env(self, monkeypatch):
        """is_mock_mode() is True when LIFI_AGENT_MOCK_MODE=1."""
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        assert client.is_mock_mode() is True

    def test_is_mock_mode_via_flag(self, monkeypatch):
        """is_mock_mode() is True when _mock_mode flag is set."""
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        client = MCPClient()
        client._mock_mode = True
        assert client.is_mock_mode() is True

    def test_is_mock_mode_after_fallback(self, monkeypatch):
        """is_mock_mode() is True after auto-fallback."""
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        monkeypatch.delenv("LIFI_AGENT_STRICT_MODE", raising=False)
        client = MCPClient(url="http://localhost:1", timeout=2)
        client.connect()
        assert client.is_mock_mode() is True


class TestMockCallReturnsDemoData:
    def test_mock_call_routes(self, monkeypatch):
        """In mock mode, call('get-supported-routes') returns demo routes."""
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        result = client.call("get-supported-routes", {})
        assert isinstance(result, list)
        assert any(r.get("fromChain") == "Base" for r in result)

    def test_mock_call_quote(self, monkeypatch):
        """In mock mode, call('request-quote') returns demo quote."""
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        result = client.call("request-quote", {"amount": "10", "fromToken": "USDC", "toToken": "USDC"})
        quotes = result.get("data", {}).get("quotes", [])
        assert len(quotes) == 1
        assert "outputAmount" in quotes[0]

    def test_mock_call_health(self, monkeypatch):
        """In mock mode, call('check-route-health') returns healthy."""
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        result = client.call("check-route-health", {})
        assert result["data"]["routeSupported"] is True

    def test_mock_call_unknown_tool(self, monkeypatch):
        """In mock mode, call() with unknown tool returns fallback message."""
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        result = client.call("unknown-tool", {})
        assert "Demo mode" in result.get("data", {}).get("message", "")


class TestLocalCallReturnsRealData:
    def test_local_call_makes_request(self, monkeypatch):
        """In local mode, call() makes a real MCP request (mocked HTTP)."""
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        client = MCPClient()
        client._mock_mode = False
        client.session_id = "test-session"
        client._connected = True

        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        payload = {"result": {"content": [{"type": "text", "text": '{"data": {"routes": []}}'}]}}
        import json
        mock_response.text = f"data: {json.dumps(payload)}\n\n"
        mock_http.post.return_value = mock_response
        client._sync_client = mock_http

        result = client.call("get-supported-routes", {})
        mock_http.post.assert_called_once()
        assert "data" in result

    def test_local_call_does_not_use_demo(self, monkeypatch):
        """In local mode, call() does not call _demo_call."""
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        client = MCPClient()
        client._mock_mode = False
        client.session_id = "test-session"
        client._connected = True

        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        import json
        payload = {"result": {"content": [{"type": "text", "text": '{"ok": true}'}]}}
        mock_response.text = f"data: {json.dumps(payload)}\n\n"
        mock_http.post.return_value = mock_response
        client._sync_client = mock_http

        with patch.object(client, '_demo_call') as mock_demo:
            client.call("get-supported-routes", {})
            mock_demo.assert_not_called()


class TestDoctorStrictMode:
    def test_doctor_strict_mode_unreachable(self):
        """Doctor with LIFI_AGENT_STRICT_MODE=1 and unreachable MCP shows clear error."""
        with patch.dict(os.environ, {"LIFI_AGENT_STRICT_MODE": "1"}, clear=False):
            os.environ.pop("LIFI_AGENT_MOCK_MODE", None)
            agent = LifAgent()
            agent.mcp = MCPClient(url="http://localhost:1", timeout=2)
            report = agent.doctor()

            # Mode group is first (index 0), Connection is second (index 1)
            mode_group = report["groups"][0]
            assert mode_group["name"] == "Mode"
            conn_group = report["groups"][1]
            assert conn_group["name"] == "Connection"
            mcp_check = conn_group["checks"][0]
            assert mcp_check["name"] == "MCP endpoint reachable"
            assert mcp_check["passed"] is False

    def test_doctor_strict_mode_no_mock_fallback(self):
        """Doctor with strict mode does not fall back to mock mode."""
        with patch.dict(os.environ, {"LIFI_AGENT_STRICT_MODE": "1"}, clear=False):
            os.environ.pop("LIFI_AGENT_MOCK_MODE", None)
            agent = LifAgent()
            agent.mcp = MCPClient(url="http://localhost:1", timeout=2)
            report = agent.doctor()

            # After doctor runs (even with failed connect), mock mode should NOT be set
            # because strict mode re-raises ConnectError instead of falling back
            assert agent.mcp._mock_mode is False
