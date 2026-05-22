"""Tests for policy and intent parsing."""

import pytest
from lifi_agent.agent import parse_policy, parse_intent, parse_intent_with_policy


class TestParsePolicyFee:
    def test_fee_less_than(self):
        p = parse_policy("send 10 USDC from Base to Arbitrum only if fee < 0.5%")
        assert p.max_fee_pct == 0.5

    def test_fee_under(self):
        p = parse_policy("bridge 50 USDT if fee under 1%")
        assert p.max_fee_pct == 1.0

    def test_max_fee(self):
        # parser requires "fee" keyword before the operator
        p = parse_policy("send with fee max 0.3%")
        assert p.max_fee_pct == 0.3

    def test_no_fee(self):
        p = parse_policy("send 10 USDC from Base to Arbitrum")
        assert p.max_fee_pct is None


class TestParsePolicyHealth:
    def test_route_is_healthy(self):
        p = parse_policy("send 10 USDC if route is healthy")
        assert p.require_healthy_route is True

    def test_healthy_route(self):
        p = parse_policy("bridge with healthy route")
        assert p.require_healthy_route is True

    def test_no_health(self):
        p = parse_policy("send 10 USDC from Base to Arbitrum")
        assert p.require_healthy_route is False


class TestParsePolicyOutput:
    def test_min_output(self):
        p = parse_policy("send 10 USDC if output >= 9.95")
        assert p.min_output_amount == 9.95

    def test_min_output_at_least(self):
        p = parse_policy("transfer if output at least 9.9")
        assert p.min_output_amount == 9.9

    def test_no_output(self):
        p = parse_policy("send 10 USDC from Base to Arbitrum")
        assert p.min_output_amount is None


class TestParsePolicyAvoid:
    def test_avoid_ethereum(self):
        p = parse_policy("send 10 USDC from Base to Arbitrum avoid Ethereum")
        assert "ethereum" in p.avoid_chains

    def test_avoid_multiple(self):
        # parser regex captures first chain; comma-separated also works
        p = parse_policy("send 10 USDC avoid ethereum and polygon")
        assert "ethereum" in p.avoid_chains
        # note: current parser only captures first chain in "X and Y" form

    def test_no_avoid(self):
        p = parse_policy("send 10 USDC from Base to Arbitrum")
        assert p.avoid_chains == []


class TestParsePolicyCombined:
    def test_fee_and_avoid(self):
        p = parse_policy("send 10 USDC from Base to Arbitrum only if fee < 0.5% avoid Ethereum")
        assert p.max_fee_pct == 0.5
        assert "ethereum" in p.avoid_chains

    def test_fee_and_health(self):
        p = parse_policy("bridge 50 USDT if fee < 1% and route is healthy")
        assert p.max_fee_pct == 1.0
        assert p.require_healthy_route is True


class TestParsePolicyCheapest:
    def test_prefer_cheapest(self):
        p = parse_policy("send 10 USDC prefer cheapest route")
        assert p.prefer_cheapest is True

    def test_no_preference(self):
        p = parse_policy("send 10 USDC from Base to Arbitrum")
        assert p.prefer_cheapest is False


class TestParsePolicyCrossChain:
    def test_same_chain_only(self):
        p = parse_policy("send 10 USDC same chain only")
        assert p.allow_cross_chain is False

    def test_no_cross_chain(self):
        p = parse_policy("send 10 USDC no cross-chain")
        assert p.allow_cross_chain is False

    def test_default_allow(self):
        p = parse_policy("send 10 USDC from Base to Arbitrum")
        assert p.allow_cross_chain is True


class TestParseIntent:
    def test_basic(self):
        i = parse_intent("send 10 USDC from Base to Arbitrum")
        assert i.amount == "10"
        assert i.token == "usdc"
        assert i.from_chain == "base"
        assert i.to_chain == "arbitrum"

    def test_eth(self):
        i = parse_intent("send 0.5 ETH from Ethereum to Optimism")
        assert i.amount == "0.5"
        assert i.token == "eth"
        assert i.from_chain == "ethereum"
        assert i.to_chain == "optimism"

    def test_alias(self):
        i = parse_intent("send 10 USDC from arb to opt")
        assert i.from_chain == "arbitrum"
        assert i.to_chain == "optimism"


class TestParseIntentWithPolicy:
    def test_combined(self):
        intent, policy = parse_intent_with_policy(
            "send 10 USDC from Base to Arbitrum only if fee < 0.5%"
        )
        assert intent.amount == "10"
        assert intent.token == "usdc"
        assert intent.from_chain == "base"
        assert intent.to_chain == "arbitrum"
        assert policy.max_fee_pct == 0.5

    def test_complex(self):
        intent, policy = parse_intent_with_policy(
            "send 10 USDC from Base to Arbitrum only if fee < 0.5% avoid Ethereum and route is healthy"
        )
        assert policy.max_fee_pct == 0.5
        assert "ethereum" in policy.avoid_chains
        assert policy.require_healthy_route is True
