"""Focused tests for Safe Verdict policy constraint combinations."""

import pytest
from unittest.mock import MagicMock
from lifi_agent.agent import LifAgent, Intent, Policy


def _make_agent() -> LifAgent:
    agent = LifAgent()
    agent.mcp = MagicMock()
    agent.mcp._connected = True
    return agent


def _mock_standard(agent):
    """Standard mock: routes exist, healthy, quote returns 9.98 USDC output."""
    def side_effect(tool, args=None):
        if tool == "get-supported-routes":
            return [
                {"fromChainId": 8453, "toChainId": 42161,
                 "fromChain": "Base", "toChain": "Arbitrum",
                 "fromToken": {"symbol": "USDC", "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"}},
            ]
        if tool == "check-route-health":
            return {"data": {"healthy": True, "status": "healthy"}}
        if tool == "request-quote":
            return {
                "data": {
                    "quotes": [{
                        "inputAmount": "10 USDC",
                        "outputAmount": "9.980000 USDC",
                        "quoteId": "test-quote-001",
                    }]
                }
            }
        return {"error": f"Unexpected tool: {tool}"}
    agent.mcp.call.side_effect = side_effect


def _mock_unhealthy(agent):
    def side_effect(tool, args=None):
        if tool == "get-supported-routes":
            return [
                {"fromChainId": 8453, "toChainId": 42161,
                 "fromChain": "Base", "toChain": "Arbitrum",
                 "fromToken": {"symbol": "USDC", "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"}},
            ]
        if tool == "check-route-health":
            return {"data": {"healthy": False, "status": "unhealthy"}}
        if tool == "request-quote":
            return {
                "data": {
                    "quotes": [{
                        "inputAmount": "10 USDC",
                        "outputAmount": "9.980000 USDC",
                        "quoteId": "test-quote-001",
                    }]
                }
            }
        return {"error": f"Unexpected tool: {tool}"}
    agent.mcp.call.side_effect = side_effect


def _mock_no_quote(agent):
    def side_effect(tool, args=None):
        if tool == "get-supported-routes":
            return [
                {"fromChainId": 8453, "toChainId": 42161,
                 "fromChain": "Base", "toChain": "Arbitrum",
                 "fromToken": {"symbol": "USDC", "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"}},
            ]
        if tool == "check-route-health":
            return {"data": {"healthy": True, "status": "healthy"}}
        if tool == "request-quote":
            return {"data": {"quotes": []}}
        return {"error": f"Unexpected tool: {tool}"}
    agent.mcp.call.side_effect = side_effect


# ── Fee constraint ────────────────────────────────────────────────

class TestFeeConstraint:
    def test_fee_pass(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(max_fee_pct=0.5)
        )
        assert verdict.executable is True

    def test_fee_fail(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(max_fee_pct=0.1)
        )
        assert verdict.executable is False


# ── Min output constraint ─────────────────────────────────────────

class TestMinOutputConstraint:
    def test_min_output_pass(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(min_output_amount=9.9)
        )
        assert verdict.executable is True

    def test_min_output_fail(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(min_output_amount=9.99)
        )
        assert verdict.executable is False


# ── Avoid chain constraint ────────────────────────────────────────

class TestAvoidChainConstraint:
    def test_avoid_pass(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(avoid_chains=["ethereum"])
        )
        assert verdict.executable is True

    def test_avoid_fail_source(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(avoid_chains=["base"])
        )
        assert verdict.executable is False

    def test_avoid_fail_target(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(avoid_chains=["arbitrum"])
        )
        assert verdict.executable is False


# ── Health constraint ─────────────────────────────────────────────

class TestHealthConstraint:
    def test_health_pass(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(require_healthy_route=True)
        )
        assert verdict.executable is True

    def test_health_fail(self):
        agent = _make_agent()
        _mock_unhealthy(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(require_healthy_route=True)
        )
        assert verdict.executable is False


# ── Cross-chain blocked ───────────────────────────────────────────

class TestCrossChainBlocked:
    def test_cross_chain_blocked(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(allow_cross_chain=False)
        )
        assert verdict.executable is False

    def test_same_chain_allowed(self):
        agent = _make_agent()
        # Include a base→base route in the mock
        def side_effect(tool, args=None):
            if tool == "get-supported-routes":
                return [
                    {"fromChainId": 8453, "toChainId": 8453,
                     "fromChain": "Base", "toChain": "Base",
                     "fromToken": {"symbol": "USDC", "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"}},
                ]
            if tool == "request-quote":
                return {"data": {"quotes": [{"inputAmount": "10 USDC",
                                              "outputAmount": "9.980000 USDC",
                                              "quoteId": "q1"}]}}
            return {"error": f"Unexpected: {tool}"}
        agent.mcp.call.side_effect = side_effect
        verdict = agent.safe_verdict(
            Intent("base", "base", "usdc", "10"),
            Policy(allow_cross_chain=False)
        )
        assert verdict.executable is True


# ── Cheapest route ────────────────────────────────────────────────

class TestCheapestRoute:
    def test_cheapest_route_passes(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(prefer_cheapest=True, max_fee_pct=0.5)
        )
        assert verdict.executable is True


# ── No quote ──────────────────────────────────────────────────────

class TestNoQuote:
    def test_no_quote_refused(self):
        agent = _make_agent()
        _mock_no_quote(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(max_fee_pct=1.0)
        )
        assert verdict.executable is False


# ── Combined constraints ──────────────────────────────────────────

class TestCombinedConstraints:
    def test_fee_and_avoid_both_pass(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(max_fee_pct=0.5, avoid_chains=["ethereum"])
        )
        assert verdict.executable is True

    def test_fee_pass_avoid_fail(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(max_fee_pct=0.5, avoid_chains=["arbitrum"])
        )
        assert verdict.executable is False

    def test_fee_fail_avoid_pass(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(max_fee_pct=0.01, avoid_chains=["ethereum"])
        )
        assert verdict.executable is False

    def test_all_constraints_pass(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(
                max_fee_pct=0.5,
                min_output_amount=9.9,
                require_healthy_route=True,
                avoid_chains=["ethereum"],
                allow_cross_chain=True,
            )
        )
        assert verdict.executable is True

    def test_all_constraints_one_fails(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(
                max_fee_pct=0.5,
                min_output_amount=9.99,  # fails: 9.98 < 9.99
                require_healthy_route=True,
                avoid_chains=["ethereum"],
            )
        )
        assert verdict.executable is False

    def test_health_and_fee_pass(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(require_healthy_route=True, max_fee_pct=0.5)
        )
        assert verdict.executable is True

    def test_health_pass_fee_fail(self):
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(require_healthy_route=True, max_fee_pct=0.01)
        )
        assert verdict.executable is False


# ── Edge cases ────────────────────────────────────────────────────

class TestEdgeCases:
    def test_fee_exactly_at_limit(self):
        """fee == limit should pass (<= comparison)."""
        agent = _make_agent()
        _mock_standard(agent)
        # fee = (10 - 9.98) / 10 * 100 = 0.20%
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(max_fee_pct=0.20)
        )
        assert verdict.executable is True

    def test_output_exactly_at_min(self):
        """output == min should pass (>= comparison)."""
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(min_output_amount=9.98)
        )
        assert verdict.executable is True

    def test_empty_avoid_list(self):
        """Empty avoid list should not block."""
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy(avoid_chains=[])
        )
        assert verdict.executable is True

    def test_no_constraints(self):
        """No policy constraints should always pass if quote exists."""
        agent = _make_agent()
        _mock_standard(agent)
        verdict = agent.safe_verdict(
            Intent("base", "arbitrum", "usdc", "10"),
            Policy()
        )
        assert verdict.executable is True
