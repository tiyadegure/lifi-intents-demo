"""Tests for demo mode (LIFI_AGENT_DEMO_MODE=1)."""

import os
import pytest


@pytest.fixture(autouse=True)
def enable_demo_mode(monkeypatch):
    monkeypatch.setenv("LIFI_AGENT_DEMO_MODE", "1")


class TestDemoModeVerdict:
    def test_executable(self):
        from lifi_agent.agent import LifAgent, Intent, Policy
        agent = LifAgent()
        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=0.5)
        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is True

    def test_refused_fee(self):
        from lifi_agent.agent import LifAgent, Intent, Policy
        agent = LifAgent()
        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=0.1)  # 0.20% > 0.1%
        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is False

    def test_fee_is_0_20_percent(self):
        from lifi_agent.agent import LifAgent, Intent, Policy
        agent = LifAgent()
        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=1.0)
        verdict = agent.safe_verdict(intent, policy)
        fee_check = [c for c in verdict.checks if c["name"] == "Fee Calculated"][0]
        assert "0.20" in fee_check["detail"]

    def test_decision_trace(self):
        from lifi_agent.agent import LifAgent, Intent, Policy
        agent = LifAgent()
        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=0.5)
        result = agent.safe_verdict_trace(intent, policy)
        assert result.verdict == "EXECUTABLE"
        assert len(result.steps) >= 5


class TestDemoModeTools:
    def test_routes(self):
        from lifi_agent.agent import LifAgent
        agent = LifAgent()
        result = agent.get_routes()
        routes = result.get("data", {}).get("routes", [])
        assert len(routes) >= 2

    def test_route_health(self):
        from lifi_agent.agent import LifAgent
        agent = LifAgent()
        result = agent.check_route_health("base", "arbitrum")
        assert result["data"]["healthy"] is True

    def test_quote(self):
        from lifi_agent.agent import LifAgent, Intent
        agent = LifAgent()
        intent = Intent("base", "arbitrum", "usdc", "10")
        result = agent.get_quote(intent)
        quotes = result.get("data", {}).get("quotes", [])
        assert len(quotes) == 1
        assert quotes[0]["quoteId"] == "demo-quote-001"
