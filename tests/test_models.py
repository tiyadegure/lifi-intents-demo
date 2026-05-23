"""Tests for models: Intent methods, Policy repr, parse_amount_with_symbol."""

import pytest
from lifi_agent.models import (
    Intent, Policy, CHAINS, parse_amount_with_symbol,
    amount_to_raw, raw_to_amount, normalize_output_amount,
)


# ── Intent.chain_id ───────────────────────────────────────────────

class TestIntentChainId:
    def test_from_chain_id_ethereum(self):
        i = Intent("ethereum", "base", "usdc", "10")
        assert i.from_chain_id() == "1"

    def test_to_chain_id_arbitrum(self):
        i = Intent("base", "arbitrum", "usdc", "10")
        assert i.to_chain_id() == "42161"

    def test_from_chain_id_base(self):
        i = Intent("base", "ethereum", "usdc", "10")
        assert i.from_chain_id() == "8453"

    def test_chain_id_polygon(self):
        i = Intent("polygon", "optimism", "usdc", "10")
        assert i.from_chain_id() == "137"
        assert i.to_chain_id() == "10"


# ── Intent.chain_name ─────────────────────────────────────────────

class TestIntentChainName:
    def test_from_chain_name(self):
        i = Intent("arbitrum", "base", "usdc", "10")
        assert i.from_chain_name() == "arbitrum"

    def test_to_chain_name(self):
        i = Intent("base", "optimism", "usdc", "10")
        assert i.to_chain_name() == "optimism"

    def test_chain_name_preserves_case(self):
        """chain_name() returns the stored value as-is."""
        i = Intent("Ethereum", "Base", "usdc", "10")
        assert i.from_chain_name() == "Ethereum"
        assert i.to_chain_name() == "Base"


# ── Intent.token_symbol ───────────────────────────────────────────

class TestIntentTokenSymbol:
    def test_usdc(self):
        i = Intent("base", "arbitrum", "usdc", "10")
        assert i.token_symbol() == "USDC"

    def test_eth(self):
        i = Intent("base", "arbitrum", "eth", "1")
        assert i.token_symbol() == "ETH"

    def test_uppercase_input(self):
        """token is always stored lowercase."""
        i = Intent("base", "arbitrum", "USDT", "10")
        assert i.token_symbol() == "USDT"

    def test_mixed_case(self):
        i = Intent("base", "arbitrum", "UsDc", "10")
        assert i.token_symbol() == "USDC"


# ── Intent.token_address ──────────────────────────────────────────

class TestIntentTokenAddress:
    def test_usdc_on_base(self):
        i = Intent("base", "arbitrum", "usdc", "10")
        addr = i.from_token_address()
        assert addr.startswith("0x")
        assert len(addr) == 42

    def test_eth_on_ethereum(self):
        i = Intent("ethereum", "base", "eth", "1")
        addr = i.from_token_address()
        assert addr.startswith("0x")

    def test_unknown_token_returns_empty(self):
        i = Intent("base", "arbitrum", "dai", "10")
        assert i.from_token_address() == ""

    def test_to_token_address(self):
        i = Intent("base", "arbitrum", "usdc", "10")
        addr = i.to_token_address()
        assert addr.startswith("0x")


# ── Intent.__repr__ ───────────────────────────────────────────────

class TestIntentRepr:
    def test_repr_format(self):
        i = Intent("base", "arbitrum", "usdc", "10")
        assert repr(i) == "Intent(10 USDC base→arbitrum)"

    def test_repr_token_uppercase(self):
        i = Intent("ethereum", "optimism", "eth", "0.5")
        assert "ETH" in repr(i)


# ── Policy.__repr__ ───────────────────────────────────────────────

class TestPolicyRepr:
    def test_no_constraints(self):
        p = Policy()
        assert repr(p) == "Policy(no constraints)"

    def test_fee_only(self):
        p = Policy(max_fee_pct=0.5)
        r = repr(p)
        assert "fee<0.5%" in r

    def test_healthy_route(self):
        p = Policy(require_healthy_route=True)
        assert "healthy route" in repr(p)

    def test_min_output(self):
        p = Policy(min_output_amount=9.5)
        assert "output>=9.5" in repr(p)

    def test_avoid_chains(self):
        p = Policy(avoid_chains=["ethereum", "polygon"])
        r = repr(p)
        assert "avoid" in r
        assert "ethereum" in r
        assert "polygon" in r

    def test_prefer_cheapest(self):
        p = Policy(prefer_cheapest=True)
        assert "prefer cheapest" in repr(p)

    def test_no_cross_chain(self):
        p = Policy(allow_cross_chain=False)
        assert "no cross-chain" in repr(p)

    def test_combined(self):
        p = Policy(max_fee_pct=0.5, require_healthy_route=True, prefer_cheapest=True)
        r = repr(p)
        assert "fee<0.5%" in r
        assert "healthy route" in r
        assert "prefer cheapest" in r


# ── parse_amount_with_symbol ──────────────────────────────────────

class TestParseAmountWithSymbol:
    def test_usdc(self):
        assert abs(parse_amount_with_symbol("9.980000 USDC") - 9.98) < 0.001

    def test_no_symbol(self):
        assert parse_amount_with_symbol("42.5") == 42.5

    def test_eth(self):
        assert abs(parse_amount_with_symbol("0.5 ETH") - 0.5) < 0.001

    def test_whitespace(self):
        assert parse_amount_with_symbol("  10 USDC  ") == 10.0

    def test_empty_string(self):
        assert parse_amount_with_symbol("") == 0.0

    def test_invalid(self):
        assert parse_amount_with_symbol("not-a-number") == 0.0

    def test_weth(self):
        assert abs(parse_amount_with_symbol("1.5 WETH") - 1.5) < 0.001

    def test_usdt(self):
        assert parse_amount_with_symbol("100 USDT") == 100.0


# ── amount_to_raw / round-trip ────────────────────────────────────

class TestAmountRoundTrip:
    def test_usdc_roundtrip(self):
        raw = amount_to_raw("10", "usdc")
        human = raw_to_amount(raw, "usdc")
        assert abs(human - 10.0) < 0.0001

    def test_eth_roundtrip(self):
        raw = amount_to_raw("0.5", "eth")
        human = raw_to_amount(raw, "eth")
        assert abs(human - 0.5) < 0.0001
