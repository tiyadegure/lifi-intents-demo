"""Tests for explain(), solver_aware_checks(), and safe_verdict_trace()."""
import os
os.environ["LIFI_AGENT_DEMO_MODE"] = "1"

import pytest
from lifi_agent.agent import LifAgent, Intent, Policy, parse_intent_with_policy


@pytest.fixture
def agent():
    return LifAgent()


# ── Tests: explain() ────────────────────────────────────────────────

class TestExplain:
    def test_basic_explain(self, agent):
        """explain() returns intent, policy, and execution plan."""
        result = agent.explain("send 10 USDC from Base to Arbitrum")
        assert result["intent"]["amount"] == "10"
        assert result["intent"]["token"] == "USDC"
        assert result["intent"]["from_chain"] == "base"
        assert result["intent"]["to_chain"] == "arbitrum"
        assert "description" in result["intent"]
        assert "description" in result["policy"]
        assert len(result["execution_plan"]) > 0

    def test_explain_with_fee_policy(self, agent):
        """explain() correctly identifies fee policy."""
        result = agent.explain("send 10 USDC from Base to Arbitrum if fee < 0.5%")
        assert result["policy"]["max_fee_pct"] == 0.5
        assert "0.5%" in result["policy"]["description"]
        assert any("fee" in s.lower() for s in result["execution_plan"])

    def test_explain_with_avoid(self, agent):
        """explain() correctly identifies avoid chains."""
        result = agent.explain("send 10 USDC from Base to Arbitrum avoid Ethereum")
        assert "ethereum" in result["policy"]["avoid_chains"]
        assert "Ethereum" in result["policy"]["description"]

    def test_explain_with_min_output(self, agent):
        """explain() correctly identifies min output."""
        result = agent.explain("send 10 USDC from Base to Arbitrum min output 9.5")
        assert result["policy"]["min_output_amount"] == 9.5
        assert "9.5" in result["policy"]["description"]

    def test_explain_with_healthy_route(self, agent):
        """explain() correctly identifies healthy route requirement."""
        result = agent.explain("send 10 USDC from Base to Arbitrum require healthy route")
        assert result["policy"]["require_healthy_route"] is True
        assert any("health" in s.lower() for s in result["execution_plan"])

    def test_explain_no_policy(self, agent):
        """explain() with no policy shows 'no constraints'."""
        result = agent.explain("send 10 USDC from Base to Arbitrum")
        assert "no constraints" in result["policy"]["description"].lower() or "no policy" in result["policy"]["description"].lower()

    def test_explain_combined_policies(self, agent):
        """explain() handles multiple policies."""
        result = agent.explain("send 10 USDC from Base to Arbitrum if fee < 0.5% avoid Ethereum min output 9.5")
        assert result["policy"]["max_fee_pct"] == 0.5
        assert "ethereum" in result["policy"]["avoid_chains"]
        assert result["policy"]["min_output_amount"] == 9.5

    def test_explain_chain_ids(self, agent):
        """explain() includes chain IDs in execution plan."""
        result = agent.explain("send 10 USDC from Base to Arbitrum")
        assert any("8453" in s for s in result["execution_plan"])
        assert any("42161" in s for s in result["execution_plan"])


# ── Tests: safe_verdict_trace() ─────────────────────────────────────

class TestSafeVerdictTrace:
    def test_trace_executable(self, agent):
        """safe_verdict_trace returns EXECUTABLE for valid intent."""
        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=1.0)
        result = agent.safe_verdict_trace(intent, policy)
        assert result.verdict == "EXECUTABLE"
        assert len(result.steps) > 0
        assert result.total_duration_ms >= 0

    def test_trace_refused_fee(self, agent):
        """safe_verdict_trace returns REFUSED when fee exceeds limit."""
        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=0.01)  # 0.01% is below demo 0.20%
        result = agent.safe_verdict_trace(intent, policy)
        assert result.verdict == "REFUSED"
        assert "0.20%" in result.reason or "fee" in result.reason.lower()

    def test_trace_refused_avoid(self, agent):
        """safe_verdict_trace returns REFUSED when source chain is avoided."""
        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(avoid_chains=["base"])
        result = agent.safe_verdict_trace(intent, policy)
        assert result.verdict == "REFUSED"
        assert "base" in result.reason.lower()

    def test_trace_refused_min_output(self, agent):
        """safe_verdict_trace returns REFUSED when output below minimum."""
        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(min_output_amount=100.0)  # Demo returns ~9.98
        result = agent.safe_verdict_trace(intent, policy)
        assert result.verdict == "REFUSED"
        assert "below minimum" in result.reason.lower() or "9.98" in result.reason

    def test_trace_has_all_steps(self, agent):
        """safe_verdict_trace includes all expected step names."""
        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=1.0)
        result = agent.safe_verdict_trace(intent, policy)
        step_names = [s.name for s in result.steps]
        assert "Parse Intent" in step_names
        assert "Parse Policy" in step_names
        assert "Get Quote" in step_names
        assert "Calculate Fee" in step_names

    def test_trace_skipped_health(self, agent):
        """safe_verdict_trace skips route health when not required."""
        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(require_healthy_route=False)
        result = agent.safe_verdict_trace(intent, policy)
        health_step = [s for s in result.steps if s.name == "Check Route Health"][0]
        assert health_step.status == "skipped"

    def test_trace_intent_and_policy_stored(self, agent):
        """safe_verdict_trace stores intent and policy in result."""
        intent = Intent("base", "arbitrum", "usdc", "10")
        policy = Policy(max_fee_pct=1.0)
        result = agent.safe_verdict_trace(intent, policy)
        assert result.intent is intent
        assert result.policy is policy


# ── Tests: solver_aware_checks() ────────────────────────────────────

class TestSolverAwareChecks:
    def test_basic_checks(self, agent):
        """solver_aware_checks returns route, checks, and summary."""
        result = agent.solver_aware_checks("base", "arbitrum")
        assert result["route"] == "base → arbitrum"
        assert len(result["checks"]) == 3  # health, quote availability, inventory
        assert "total_checks" in result["summary"]

    def test_check_names(self, agent):
        """solver_aware_checks includes expected check names."""
        result = agent.solver_aware_checks("base", "arbitrum")
        names = [c["name"] for c in result["checks"]]
        assert "Route Health" in names
        assert "Quote Availability" in names
        assert "Solver Inventory" in names

    def test_health_check_has_explanation(self, agent):
        """Route Health check includes explanation and action."""
        result = agent.solver_aware_checks("base", "arbitrum")
        health = [c for c in result["checks"] if c["name"] == "Route Health"][0]
        assert "explanation" in health
        assert "action" in health
        assert len(health["explanation"]) > 0
        assert len(health["action"]) > 0

    def test_quote_availability_has_explanation(self, agent):
        """Quote Availability check includes explanation and action."""
        result = agent.solver_aware_checks("base", "arbitrum")
        quote = [c for c in result["checks"] if c["name"] == "Quote Availability"][0]
        assert "explanation" in quote
        assert "action" in quote

    def test_solver_inventory_has_explanation(self, agent):
        """Solver Inventory check includes explanation and action."""
        result = agent.solver_aware_checks("base", "arbitrum", "usdc", "usdc")
        inv = [c for c in result["checks"] if c["name"] == "Solver Inventory"][0]
        assert "explanation" in inv
        assert "action" in inv

    def test_inventory_skipped_without_assets(self, agent):
        """Solver Inventory is skipped when no asset pair specified."""
        result = agent.solver_aware_checks("base", "arbitrum")
        inv = [c for c in result["checks"] if c["name"] == "Solver Inventory"][0]
        assert inv["status"] == "skipped"
        assert inv["passed"] is True

    def test_summary_counts(self, agent):
        """Summary has correct total/passed/failed counts."""
        result = agent.solver_aware_checks("base", "arbitrum")
        summary = result["summary"]
        assert summary["total_checks"] == 3
        assert summary["passed_checks"] + summary["failed_checks"] == summary["total_checks"]
        assert summary["overall_status"] in ("healthy", "degraded")
