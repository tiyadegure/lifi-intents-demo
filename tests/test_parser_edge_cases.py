"""Edge-case tests for parse_intent and parse_policy."""

import pytest
from lifi_agent.parser import parse_intent, parse_policy, parse_intent_with_policy


# ── parse_intent: arrow syntax ────────────────────────────────────

class TestIntentArrowSyntax:
    def test_arrow_dash(self):
        i = parse_intent("10 USDC base->arb")
        assert i.from_chain == "base"
        assert i.to_chain == "arbitrum"

    def test_arrow_unicode(self):
        i = parse_intent("10 USDC base→arb")
        assert i.from_chain == "base"
        assert i.to_chain == "arbitrum"

    def test_arrow_with_amounts(self):
        i = parse_intent("send 0.5 ETH eth→opt")
        assert i.amount == "0.5"
        assert i.token == "eth"
        assert i.from_chain == "ethereum"
        assert i.to_chain == "optimism"

    def test_arrow_full_names(self):
        i = parse_intent("50 USDC ethereum->polygon")
        assert i.from_chain == "ethereum"
        assert i.to_chain == "polygon"


# ── parse_intent: mixed case ──────────────────────────────────────

class TestIntentMixedCase:
    def test_all_uppercase(self):
        i = parse_intent("SEND 10 USDC FROM BASE TO ARBITRUM")
        assert i.amount == "10"
        assert i.token == "usdc"
        assert i.from_chain == "base"
        assert i.to_chain == "arbitrum"

    def test_mixed_case_chains(self):
        i = parse_intent("bridge 5 USDT from Ethereum to Optimism")
        assert i.from_chain == "ethereum"
        assert i.to_chain == "optimism"

    def test_mixed_case_token(self):
        i = parse_intent("send 1 UsDc from Base to Arbitrum")
        assert i.token == "usdc"


# ── parse_intent: decimal / small amounts ─────────────────────────

class TestIntentAmounts:
    def test_small_decimal(self):
        i = parse_intent("send 0.001 USDC from base to arbitrum")
        assert i.amount == "0.001"

    def test_large_amount(self):
        i = parse_intent("send 1000000 USDC from ethereum to base")
        assert i.amount == "1000000"

    def test_fractional_eth(self):
        i = parse_intent("send 0.0001 ETH from ethereum to optimism")
        assert i.amount == "0.0001"


# ── parse_intent: error cases ─────────────────────────────────────

class TestIntentErrors:
    def test_no_chains_raises(self):
        with pytest.raises(ValueError, match="Need two chains"):
            parse_intent("send 10 USDC")

    def test_same_chain_raises(self):
        with pytest.raises(ValueError, match="Need two chains"):
            parse_intent("send 10 USDC from base to base")

    def test_no_amount_raises(self):
        with pytest.raises(ValueError, match="Couldn't find amount"):
            parse_intent("send USDC from base to arbitrum")

    def test_unknown_chain_raises(self):
        with pytest.raises(ValueError, match="Need two chains"):
            parse_intent("send 10 USDC from moonchain to starnet")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_intent("")


# ── parse_intent: from/to pattern ─────────────────────────────────

class TestIntentFromToPattern:
    def test_from_to_explicit(self):
        i = parse_intent("send 10 USDC from optimism to base")
        assert i.from_chain == "optimism"
        assert i.to_chain == "base"

    def test_bridge_keyword(self):
        i = parse_intent("bridge 25 USDT polygon to ethereum")
        assert i.from_chain == "polygon"
        assert i.to_chain == "ethereum"

    def test_transfer_keyword(self):
        i = parse_intent("transfer 1 ETH from arbitrum to base")
        assert i.from_chain == "arbitrum"
        assert i.to_chain == "base"


# ── parse_policy: slippage ────────────────────────────────────────

class TestPolicySlippage:
    def test_slippage_less_than(self):
        p = parse_policy("send 10 USDC if slippage < 0.5%")
        assert p.max_slippage == 0.5

    def test_slippage_under(self):
        p = parse_policy("bridge with slippage under 1%")
        assert p.max_slippage == 1.0

    def test_slippage_max(self):
        p = parse_policy("slippage max 2%")
        assert p.max_slippage == 2.0

    def test_no_slippage(self):
        p = parse_policy("send 10 USDC from base to arbitrum")
        assert p.max_slippage is None


# ── parse_policy: no-quote requirement ────────────────────────────

class TestPolicyNoQuote:
    def test_do_not_execute_if_no_quote(self):
        p = parse_policy("do not execute if no quote")
        assert p.require_quote is True

    def test_no_quote_equals_no_execute(self):
        p = parse_policy("no quote = no execute")
        assert p.require_quote is True

    def test_default_require_quote(self):
        """require_quote defaults to True."""
        p = parse_policy("send 10 USDC")
        assert p.require_quote is True


# ── parse_policy: combined edge cases ─────────────────────────────

class TestPolicyCombined:
    def test_all_constraints(self):
        text = (
            "send 10 USDC from base to arbitrum "
            "only if fee < 0.5% "
            "avoid ethereum "
            "min output 9.5 "
            "slippage < 1% "
            "prefer cheapest route "
            "no cross-chain"
        )
        p = parse_policy(text)
        assert p.max_fee_pct == 0.5
        assert "ethereum" in p.avoid_chains
        assert p.min_output_amount == 9.5
        assert p.max_slippage == 1.0
        assert p.prefer_cheapest is True
        assert p.allow_cross_chain is False

    def test_empty_string(self):
        p = parse_policy("")
        assert p.max_fee_pct is None
        assert p.require_healthy_route is False
        assert p.avoid_chains == []
        assert p.prefer_cheapest is False


# ── parse_intent_with_policy: combined ────────────────────────────

class TestIntentWithPolicyEdgeCases:
    def test_full_combined(self):
        intent, policy = parse_intent_with_policy(
            "send 10 USDC from base to arbitrum only if fee < 0.5% avoid ethereum"
        )
        assert intent.from_chain == "base"
        assert intent.to_chain == "arbitrum"
        assert policy.max_fee_pct == 0.5
        assert "ethereum" in policy.avoid_chains

    def test_arrow_with_policy(self):
        intent, policy = parse_intent_with_policy(
            "10 USDC base->arb if fee < 1%"
        )
        assert intent.from_chain == "base"
        assert intent.to_chain == "arbitrum"
        assert policy.max_fee_pct == 1.0

    def test_no_policy(self):
        intent, policy = parse_intent_with_policy(
            "send 5 USDT from ethereum to optimism"
        )
        assert intent.amount == "5"
        assert policy.max_fee_pct is None
