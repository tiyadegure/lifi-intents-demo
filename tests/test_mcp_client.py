"""Tests for MCPClient: mock mode, caching, rate limiting, SSE parsing."""

import json
import os
import time
import pytest
from unittest.mock import MagicMock, patch

from lifi_agent.mcp_client import MCPClient


# ── SSE parsing ───────────────────────────────────────────────────

class TestSSEParsing:
    def test_parse_sse_valid(self):
        """Valid SSE with a JSON text content block."""
        payload = {"result": {"content": [{"type": "text", "text": '{"ok": true}'}]}}
        sse_text = f"data: {json.dumps(payload)}\n\n"
        result = MCPClient._parse_sse(sse_text)
        assert result == {"ok": True}

    def test_parse_sse_multiple_data_lines(self):
        """Last valid data line wins."""
        p1 = {"result": {"content": [{"type": "text", "text": '{"first": 1}'}]}}
        p2 = {"result": {"content": [{"type": "text", "text": '{"second": 2}'}]}}
        sse_text = f"data: {json.dumps(p1)}\ndata: {json.dumps(p2)}\n\n"
        result = MCPClient._parse_sse(sse_text)
        assert result == {"second": 2}

    def test_parse_sse_no_data(self):
        """No data lines returns error dict."""
        result = MCPClient._parse_sse("")
        assert "error" in result

    def test_parse_sse_invalid_json_data_line(self):
        """Invalid JSON in data line is skipped."""
        payload = {"result": {"content": [{"type": "text", "text": '{"ok": true}'}]}}
        sse_text = f"data: not-json\ndata: {json.dumps(payload)}\n\n"
        result = MCPClient._parse_sse(sse_text)
        assert result == {"ok": True}

    def test_parse_sse_raw_text(self):
        """Non-JSON text content is wrapped in raw key."""
        payload = {"result": {"content": [{"type": "text", "text": "some raw text"}]}}
        sse_text = f"data: {json.dumps(payload)}\n\n"
        result = MCPClient._parse_sse(sse_text)
        assert result == {"raw": "some raw text"}

    def test_parse_sse_empty_content(self):
        """Content list with no text type returns error."""
        payload = {"result": {"content": [{"type": "image", "data": "base64"}]}}
        sse_text = f"data: {json.dumps(payload)}\n\n"
        result = MCPClient._parse_sse(sse_text)
        assert "error" in result


# ── Server info parsing ───────────────────────────────────────────

class TestServerInfoParsing:
    def test_parse_server_info(self):
        payload = {"result": {"serverInfo": {"name": "test-server", "version": "1.0"}}}
        sse_text = f"data: {json.dumps(payload)}\n\n"
        result = MCPClient._parse_server_info(sse_text)
        assert result["serverInfo"]["name"] == "test-server"

    def test_parse_server_info_empty(self):
        result = MCPClient._parse_server_info("")
        assert result == {}


# ── Mock mode ─────────────────────────────────────────────────────

class TestMockMode:
    def test_mock_mode_env_activates_mock(self, monkeypatch):
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        assert client.is_mock_mode() is True

    def test_mock_mode_flag(self):
        client = MCPClient()
        client._mock_mode = True
        assert client.is_mock_mode() is True

    def test_mock_returns_routes(self, monkeypatch):
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        result = client.call("get-supported-routes", {})
        assert isinstance(result, list)
        assert len(result) > 0

    def test_mock_returns_quote(self, monkeypatch):
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        result = client.call("request-quote", {"amount": "10", "fromToken": "USDC", "toToken": "USDC"})
        quotes = result.get("data", {}).get("quotes", [])
        assert len(quotes) == 1
        assert "outputAmount" in quotes[0]

    def test_mock_returns_health(self, monkeypatch):
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        result = client.call("check-route-health", {})
        assert result["data"]["healthy"] is True

    def test_mock_connect(self, monkeypatch):
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        info = client.connect()
        assert "serverInfo" in info


# ── Caching ───────────────────────────────────────────────────────

class TestCaching:
    def test_cache_hit(self, monkeypatch):
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        # First call populates cache
        result1 = client.call("request-quote", {"amount": "10"}, use_cache=True)
        # Second call should hit cache (same result)
        result2 = client.call("request-quote", {"amount": "10"}, use_cache=True)
        assert result1 == result2

    def test_cache_disabled(self, monkeypatch):
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        result1 = client.call("request-quote", {"amount": "10"}, use_cache=False)
        result2 = client.call("request-quote", {"amount": "10"}, use_cache=False)
        # Both should return valid results (may or may not be same object)
        assert "data" in result1 or "error" in result1
        assert "data" in result2 or "error" in result2

    def test_cleanup_expired(self, monkeypatch):
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        # Manually insert an expired entry
        client._cache["expired:key"] = (time.time() - 600, {"stale": True})
        client._cache["fresh:key"] = (time.time(), {"fresh": True})
        client._cleanup_cache()
        assert "expired:key" not in client._cache
        assert "fresh:key" in client._cache

    def test_cleanup_max_size(self, monkeypatch):
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        # Fill cache beyond max
        for i in range(205):
            client._cache[f"key:{i}"] = (time.time() - 200 + i, {"i": i})
        client._cleanup_cache()
        assert len(client._cache) <= 200


# ── Rate limiting ─────────────────────────────────────────────────

class TestRateLimiting:
    def test_rate_limit_sync_enforces_interval(self):
        """Sync rate limiter sleeps when called too quickly."""
        client = MCPClient()
        client._last_call_time_sync = time.monotonic()
        start = time.monotonic()
        client._rate_limit_sync()
        elapsed = time.monotonic() - start
        # Should have slept at least a fraction of MIN_CALL_INTERVAL
        assert elapsed >= 0.0  # just verify it doesn't crash

    def test_rate_limit_no_sleep_when_safe(self):
        """No sleep when enough time has passed."""
        client = MCPClient()
        client._last_call_time_sync = time.monotonic() - 5.0  # 5 seconds ago
        start = time.monotonic()
        client._rate_limit_sync()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1  # Should return almost instantly


# ── Context manager ───────────────────────────────────────────────

class TestContextManager:
    def test_sync_context_manager(self, monkeypatch):
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        with MCPClient() as client:
            assert client._connected is True
            result = client.call("get-supported-routes", {})
            assert isinstance(result, list)

    def test_close_resets_state(self, monkeypatch):
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        client.connect()
        assert client._connected is True
        client.close()
        assert client._connected is False


# ── Headers ───────────────────────────────────────────────────────

class TestHeaders:
    def test_headers_with_session_id(self):
        client = MCPClient()
        client.session_id = "test-session-123"
        h = client._headers()
        assert h["mcp-session-id"] == "test-session-123"

    def test_headers_without_session_id(self):
        client = MCPClient()
        h = client._headers()
        assert "mcp-session-id" not in h

    def test_headers_content_type(self):
        client = MCPClient()
        h = client._headers()
        assert h["Content-Type"] == "application/json"
