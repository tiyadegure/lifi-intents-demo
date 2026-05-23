"""Focused tests for amount conversion edge cases."""

import pytest
from decimal import Decimal
from lifi_agent.models import (
    parse_amount_with_symbol,
    normalize_output_amount,
    amount_to_raw,
    raw_to_amount,
)


class TestParseAmountWithSymbolEdgeCases:
    """Edge cases for parse_amount_with_symbol."""

    def test_negative(self):
        assert parse_amount_with_symbol("-1.5 USDC") == -1.5

    def test_very_large(self):
        result = parse_amount_with_symbol("999999999.999999 USDC")
        assert abs(result - 999999999.999999) < 0.001

    def test_scientific_notation(self):
        # float() handles scientific notation
        result = parse_amount_with_symbol("1e6 USDC")
        assert result == 1000000.0

    def test_zero(self):
        assert parse_amount_with_symbol("0 USDC") == 0.0

    def test_zero_no_symbol(self):
        assert parse_amount_with_symbol("0") == 0.0

    def test_multiple_spaces(self):
        assert parse_amount_with_symbol("10   USDC") == 10.0

    def test_leading_trailing_spaces(self):
        assert parse_amount_with_symbol("   0.5 ETH   ") == 0.5

    def test_weth_symbol(self):
        assert parse_amount_with_symbol("2.5 WETH") == 2.5

    def test_dai_symbol(self):
        assert parse_amount_with_symbol("100 DAI") == 100.0

    def test_no_space_before_symbol(self):
        # "10USDC" — no space before symbol
        # The code also does .replace(symbol, '') without space, so this works
        result = parse_amount_with_symbol("10USDC")
        assert result == 10.0

    def test_none_input(self):
        assert parse_amount_with_symbol(None) == 0.0

    def test_whitespace_only(self):
        assert parse_amount_with_symbol("   ") == 0.0


class TestNormalizeOutputAmountNewFormat:
    """normalize_output_amount with new '0.978879 USDC' format."""

    def test_new_format_basic(self):
        result = normalize_output_amount("0.978879 USDC", "1", "usdc")
        assert abs(result - 0.978879) < 0.000001

    def test_new_format_with_spaces(self):
        result = normalize_output_amount("  9.98 USDC  ", "10", "usdc")
        assert abs(result - 9.98) < 0.001

    def test_new_format_eth(self):
        result = normalize_output_amount("0.998 ETH", "1", "eth")
        assert abs(result - 0.998) < 0.001

    def test_new_format_usdt(self):
        result = normalize_output_amount("50 USDT", "50", "usdt")
        assert result == 50.0

    def test_new_format_weth(self):
        result = normalize_output_amount("1.5 WETH", "1.5", "weth")
        assert result == 1.5


class TestNormalizeOutputAmountOldRawFormat:
    """normalize_output_amount with old raw format like '9980000'."""

    def test_raw_usdc(self):
        result = normalize_output_amount("9980000", "10", "usdc")
        assert abs(result - 9.98) < 0.001

    def test_raw_eth(self):
        result = normalize_output_amount("998000000000000000", "1", "eth")
        assert abs(result - 0.998) < 0.001

    def test_raw_usdt(self):
        result = normalize_output_amount("100000000", "100", "usdt")
        assert result == 100.0

    def test_human_readable_no_conversion(self):
        # "9.98" with input "10" — 9.98 < 10*1000 so it stays as-is
        result = normalize_output_amount("9.98", "10", "usdc")
        assert abs(result - 9.98) < 0.001

    def test_zero_raw(self):
        result = normalize_output_amount("0", "10", "usdc")
        assert result == 0.0


class TestAmountToRawDecimalPrecision:
    """amount_to_raw with Decimal precision for ETH 18 decimals."""

    def test_eth_one(self):
        result = amount_to_raw("1", "eth")
        assert result == "1000000000000000000"

    def test_eth_small_decimal(self):
        result = amount_to_raw("0.000000000000000001", "eth")
        assert result == "1"

    def test_eth_fractional(self):
        result = amount_to_raw("0.5", "eth")
        assert result == "500000000000000000"

    def test_eth_large(self):
        result = amount_to_raw("1000000", "eth")
        assert result == "1000000000000000000000000"

    def test_usdc_precision(self):
        result = amount_to_raw("0.000001", "usdc")
        assert result == "1"

    def test_weth_18_decimals(self):
        result = amount_to_raw("1", "weth")
        assert result == "1000000000000000000"

    def test_roundtrip_eth(self):
        raw = amount_to_raw("0.123456789", "eth")
        human = raw_to_amount(raw, "eth")
        assert abs(human - 0.123456789) < 1e-12

    def test_roundtrip_usdc(self):
        raw = amount_to_raw("99.999999", "usdc")
        human = raw_to_amount(raw, "usdc")
        assert abs(human - 99.999999) < 0.001
