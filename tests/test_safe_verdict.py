"""Tests for Safe Verdict logic with mocked MCP."""

import pytest
from unittest.mock import MagicMock, patch
from lifi_agent.agent import (
    LifAgent, Intent, Policy, Verdict, DecisionResult,
    normalize_output_amount,
)


# ── Helpers ────────────────────────────────────────────────────────

def _make_agent() -> LifAgent:
    """Create a LifAgent with a mocked MCP client."""
    agent = LifAgent()
    agent.mcp = MagicMock()
    agent.mcp._connected = True
    return agent


def _mock_mcp_routes(agent, routes=None):
    """Configure mock to return supported routes."""
    if routes is None:
        routes = [
            {"fromChainId": 8453, "toChainId": 42161,
             "fromToken": {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"}},
        ]

    def side_effect(tool, args=None):
        if tool == "get-supported-routes":
            return {"data": {"routes": routes}}
        if tool == "check-route-health":
            return {"data": {"healthy": True, "status": "healthy"}}
        if tool == "request-quote":
            return {
                "data": {
                    "quotes": [{
                        "inputAmount": "10000000",
                        "outputAmount": "9980000",
                        "quoteId": "test-quote-001",
                    }]
                }
            }
        return {"error": f"Unexpected tool: {tool}"}

    agent.mcp.call.side_effect = side_effect


def _mock_mcp_no_quote(agent):
    """Configure mock to return no quotes."""
    def side_effect(tool, args=None):
        if tool == "get-supported-routes":
            return {"data": {"routes": [
                {"fromChainId": 8453, "toChainId": 42161,
                 "fromToken": {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"}},
            ]}}
        if tool == "check-route-health":
            return {"data": {"healthy": True, "status": "healthy"}}
        if tool == "request-quote":
            return {"data": {"quotes": []}}
        return {"error": f"Unexpected tool: {tool}"}

    agent.mcp.call.side_effect = side_effect


def _mock_mcp_unhealthy(agent):
    """Configure mock to return unhealthy route."""
    def side_effect(tool, args=None):
        if tool == "get-supported-routes":
            return {"data": {"routes": [
                {"fromChainId": 8453, "toChainId": 42161,
                 "fromToken": {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"}},
            ]}}
        if tool == "check-route-health":
            return {"data": {"healthy": False, "status": "unhealthy"}}
        if tool == "request-quote":
            return {
                "data": {
                    "quotes": [{
                        "inputAmount": "10000000",
                        "outputAmount": "9980000",
                        "quoteId": "test-quote-001",
                    }]
                }
            }
        return {"error": f"Unexpected tool: {tool}"}

    agent.mcp.call.side_effect = side_effect


# ── Tests: Verdict with fee policy ─────────────────────────────────

class TestSafeVerdictFee:
    def test_fee_below_limit_executable(self):
        """fee 0.20% < limit 0.5% → EXECUTABLE"""
        agent = _make_agent()
        _mock_mcp_routes(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=0.5)

        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is True

    def test_fee_above_limit_refused(self):
        """fee 0.20% > limit 0.1% → REFUSED"""
        agent = _make_agent()
        _mock_mcp_routes(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=0.1)

        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is False

    def test_fee_exact_limit_executable(self):
        """fee == limit → EXECUTABLE (<=)"""
        agent = _make_agent()
        # output 9980000 raw = 9.98, fee = (10 - 9.98) / 10 = 0.20%
        _mock_mcp_routes(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=0.20)

        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is True


# ── Tests: Verdict with min output policy ──────────────────────────

class TestSafeVerdictMinOutput:
    def test_output_above_min_executable(self):
        """output 9.98 >= min 9.9 → EXECUTABLE"""
        agent = _make_agent()
        _mock_mcp_routes(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(min_output_amount=9.9)

        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is True

    def test_output_below_min_refused(self):
        """output 9.98 < min 9.99 → REFUSED"""
        agent = _make_agent()
        _mock_mcp_routes(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(min_output_amount=9.99)

        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is False


# ── Tests: Verdict with avoid chains ───────────────────────────────

class TestSafeVerdictAvoidChains:
    def test_avoid_target_chain_refused(self):
        """target is in avoid list → REFUSED"""
        agent = _make_agent()
        _mock_mcp_routes(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(avoid_chains=["arbitrum"])

        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is False

    def test_avoid_source_chain_refused(self):
        """source is in avoid list → REFUSED"""
        agent = _make_agent()
        _mock_mcp_routes(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(avoid_chains=["base"])

        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is False

    def test_avoid_both_chains_refused(self):
        """both source and target in avoid list → REFUSED"""
        agent = _make_agent()
        _mock_mcp_routes(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(avoid_chains=["base", "arbitrum"])

        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is False

    def test_avoid_other_chain_executable(self):
        """avoid list doesn't include target → EXECUTABLE"""
        agent = _make_agent()
        _mock_mcp_routes(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(avoid_chains=["ethereum"])

        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is True


# ── Tests: Verdict with route health ───────────────────────────────

class TestSafeVerdictRouteHealth:
    def test_healthy_route_executable(self):
        """route healthy + policy requires it → EXECUTABLE"""
        agent = _make_agent()
        _mock_mcp_routes(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(require_healthy_route=True, max_fee_pct=0.5)

        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is True

    def test_unhealthy_route_refused(self):
        """route unhealthy + policy requires it → REFUSED"""
        agent = _make_agent()
        _mock_mcp_unhealthy(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(require_healthy_route=True)

        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is False

    def test_health_not_required_skips(self):
        """policy doesn't require health → skip check, still EXECUTABLE"""
        agent = _make_agent()
        _mock_mcp_unhealthy(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(require_healthy_route=False, max_fee_pct=0.5)

        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is True


# ── Tests: No quote ────────────────────────────────────────────────

class TestSafeVerdictNoQuote:
    def test_no_quote_refused(self):
        """no quotes returned → REFUSED"""
        agent = _make_agent()
        _mock_mcp_no_quote(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=0.5)

        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is False


# ── Tests: Decision Trace ──────────────────────────────────────────

class TestDecisionTrace:
    def test_trace_has_all_steps(self):
        """trace should contain all expected steps"""
        agent = _make_agent()
        _mock_mcp_routes(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=0.5)

        result = agent.safe_verdict_trace(intent, policy)
        step_names = [s.name for s in result.steps]

        assert "Parse Intent" in step_names
        assert "Parse Policy" in step_names
        assert "Check Supported Route" in step_names
        assert "Get Quote" in step_names
        assert "Calculate Fee" in step_names

    def test_trace_verdict_executable(self):
        agent = _make_agent()
        _mock_mcp_routes(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=0.5)

        result = agent.safe_verdict_trace(intent, policy)
        assert result.verdict == "EXECUTABLE"

    def test_trace_verdict_refused(self):
        agent = _make_agent()
        _mock_mcp_routes(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=0.01)  # very strict

        result = agent.safe_verdict_trace(intent, policy)
        assert result.verdict == "REFUSED"

    def test_trace_has_timing(self):
        agent = _make_agent()
        _mock_mcp_routes(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=0.5)

        result = agent.safe_verdict_trace(intent, policy)
        assert result.total_duration_ms >= 0
        for step in result.steps:
            assert step.duration_ms >= 0


# ── Tests: Combined policy ─────────────────────────────────────────

class TestSafeVerdictCombined:
    def test_fee_and_avoid_both_pass(self):
        agent = _make_agent()
        _mock_mcp_routes(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=0.5, avoid_chains=["ethereum"])

        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is True

    def test_fee_pass_avoid_fail(self):
        agent = _make_agent()
        _mock_mcp_routes(agent)

        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=0.5, avoid_chains=["arbitrum"])

        verdict = agent.safe_verdict(intent, policy)
        assert verdict.executable is False
