"""Tests for MCPClient.mode property and _mock_fallback distinction."""

import os
import pytest
from unittest.mock import patch, MagicMock

from lifi_agent.mcp_client import MCPClient


class TestModeProperty:
    """Test the mode property returns correct values."""

    def test_mode_local_mcp_by_default(self, monkeypatch):
        """Default mode is local_mcp when no env vars set."""
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        monkeypatch.delenv("LIFI_AGENT_STRICT_MODE", raising=False)
        monkeypatch.delenv("LIFI_AGENT_DEMO_MODE", raising=False)
        client = MCPClient()
        assert client.mode == "local_mcp"

    def test_mode_mock_forced(self, monkeypatch):
        """LIFI_AGENT_MOCK_MODE=1 → mock_forced."""
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        assert client.mode == "mock_forced"

    def test_mode_mock_forced_deprecated(self, monkeypatch):
        """LIFI_AGENT_DEMO_MODE=1 (deprecated) → mock_forced."""
        monkeypatch.setenv("LIFI_AGENT_DEMO_MODE", "1")
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        client = MCPClient()
        assert client.mode == "mock_forced"

    def test_mode_strict(self, monkeypatch):
        """LIFI_AGENT_STRICT_MODE=1 → strict."""
        monkeypatch.setenv("LIFI_AGENT_STRICT_MODE", "1")
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        client = MCPClient()
        assert client.mode == "strict"

    def test_mode_mock_fallback_after_connect(self, monkeypatch):
        """Auto-fallback on bad port → mock_fallback."""
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        monkeypatch.delenv("LIFI_AGENT_STRICT_MODE", raising=False)
        client = MCPClient(url="http://localhost:1", timeout=2)
        assert client.mode == "local_mcp"  # Before connect
        client.connect()
        assert client.mode == "mock_fallback"  # After fallback

    def test_mock_fallback_flag_set(self, monkeypatch):
        """_mock_fallback is True after auto-fallback, False when forced."""
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        client = MCPClient(url="http://localhost:1", timeout=2)
        assert client._mock_fallback is False
        client.connect()
        assert client._mock_fallback is True

    def test_mock_forced_fallback_flag_not_set(self, monkeypatch):
        """_mock_fallback is False when mock is forced via env var."""
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        client.connect()
        assert client._mock_fallback is False


class TestMockModeSource:
    """Test mock_mode_source() returns correct reasons."""

    def test_source_not_in_mock(self, monkeypatch):
        """Empty string when not in mock mode."""
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        monkeypatch.delenv("LIFI_AGENT_DEMO_MODE", raising=False)
        client = MCPClient()
        assert client.mock_mode_source() == ""

    def test_source_forced_mock(self, monkeypatch):
        """Returns LIFI_AGENT_MOCK_MODE=1 when forced."""
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        assert "LIFI_AGENT_MOCK_MODE" in client.mock_mode_source()

    def test_source_deprecated_demo(self, monkeypatch):
        """Returns deprecated notice for LIFI_AGENT_DEMO_MODE."""
        monkeypatch.setenv("LIFI_AGENT_DEMO_MODE", "1")
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        client = MCPClient()
        source = client.mock_mode_source()
        assert "DEMO_MODE" in source
        assert "deprecated" in source

    def test_source_auto_fallback(self, monkeypatch):
        """Returns auto-fallback when connection fails."""
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        client = MCPClient(url="http://localhost:1", timeout=2)
        client.connect()
        assert "auto-fallback" in client.mock_mode_source()


class TestInitMockCheck:
    """Test that _is_mock_forced() is checked once at __init__."""

    def test_init_sets_mock_mode_from_env(self, monkeypatch):
        """__init__ sets _mock_mode from env var."""
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        assert client._mock_mode is True

    def test_init_default_no_mock(self, monkeypatch):
        """__init__ sets _mock_mode=False by default."""
        monkeypatch.delenv("LIFI_AGENT_MOCK_MODE", raising=False)
        monkeypatch.delenv("LIFI_AGENT_DEMO_MODE", raising=False)
        client = MCPClient()
        assert client._mock_mode is False

    def test_connect_uses_init_mock_flag(self, monkeypatch):
        """connect() respects _mock_mode set at init, no redundant check."""
        monkeypatch.setenv("LIFI_AGENT_MOCK_MODE", "1")
        client = MCPClient()
        # connect() should not make HTTP requests
        mock_http = MagicMock()
        client._sync_client = mock_http
        client.connect()
        mock_http.post.assert_not_called()
