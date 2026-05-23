"""Tests for amount conversion functions."""

import pytest
from lifi_agent.agent import amount_to_raw, raw_to_amount, normalize_output_amount
from lifi_agent.models import parse_amount_with_symbol


class TestAmountToRaw:
    def test_usdc_10(self):
        assert amount_to_raw("10", "usdc") == "10000000"

    def test_usdc_1(self):
        assert amount_to_raw("1", "usdc") == "1000000"

    def test_usdc_0_5(self):
        assert amount_to_raw("0.5", "usdc") == "500000"

    def test_usdt_100(self):
        assert amount_to_raw("100", "usdt") == "100000000"

    def test_eth_1(self):
        assert amount_to_raw("1", "eth") == "1000000000000000000"

    def test_eth_0_1(self):
        assert amount_to_raw("0.1", "eth") == "100000000000000000"

    def test_weth_1(self):
        assert amount_to_raw("1", "weth") == "1000000000000000000"

    def test_invalid_input(self):
        assert amount_to_raw("abc", "usdc") == "abc"


class TestRawToAmount:
    def test_usdc_10(self):
        assert raw_to_amount("10000000", "usdc") == 10.0

    def test_usdc_9_98(self):
        assert raw_to_amount("9980000", "usdc") == 9.98

    def test_usdc_1(self):
        assert raw_to_amount("1000000", "usdc") == 1.0

    def test_usdt_100(self):
        assert raw_to_amount("100000000", "usdt") == 100.0

    def test_eth_1(self):
        assert raw_to_amount("1000000000000000000", "eth") == 1.0

    def test_eth_0_5(self):
        assert raw_to_amount("500000000000000000", "eth") == 0.5

    def test_invalid_input(self):
        assert raw_to_amount("abc", "usdc") == 0.0


class TestNormalizeOutputAmount:
    """normalize_output_amount should detect raw vs human-readable."""

    def test_raw_usdc(self):
        # 9980000 is raw, input is 10 -> should convert to 9.98
        result = normalize_output_amount("9980000", "10", "usdc")
        assert abs(result - 9.98) < 0.001

    def test_human_usdc(self):
        # 9.98 is already human-readable
        result = normalize_output_amount("9.98", "10", "usdc")
        assert abs(result - 9.98) < 0.001

    def test_raw_eth(self):
        # 998000000000000000 is raw ETH, input is 1
        result = normalize_output_amount("998000000000000000", "1", "eth")
        assert abs(result - 0.998) < 0.001

    def test_human_eth(self):
        # 0.998 is already human-readable
        result = normalize_output_amount("0.998", "1", "eth")
        assert abs(result - 0.998) < 0.001

    def test_exact_match(self):
        # output == input (no fee)
        result = normalize_output_amount("10000000", "10", "usdc")
        assert result == 10.0

    def test_zero(self):
        result = normalize_output_amount("0", "10", "usdc")
        assert result == 0.0


class TestParseAmountWithSymbol:
    """parse_amount_with_symbol handles new MCP format like '0.978879 USDC'."""

    def test_usdc(self):
        assert abs(parse_amount_with_symbol("0.978879 USDC") - 0.978879) < 0.000001

    def test_usdc_whole(self):
        assert parse_amount_with_symbol("10 USDC") == 10.0

    def test_eth(self):
        assert abs(parse_amount_with_symbol("0.5 ETH") - 0.5) < 0.001

    def test_usdt(self):
        assert parse_amount_with_symbol("100 USDT") == 100.0

    def test_no_symbol(self):
        assert parse_amount_with_symbol("9.98") == 9.98

    def test_invalid(self):
        assert parse_amount_with_symbol("abc") == 0.0

    def test_empty(self):
        assert parse_amount_with_symbol("") == 0.0


class TestNormalizeOutputNewFormat:
    """normalize_output_amount handles new '0.978879 USDC' format."""

    def test_new_format_usdc(self):
        result = normalize_output_amount("9.980000 USDC", "10", "usdc")
        assert abs(result - 9.98) < 0.001

    def test_new_format_eth(self):
        result = normalize_output_amount("0.998000 ETH", "1", "eth")
        assert abs(result - 0.998) < 0.001

    def test_new_format_small(self):
        result = normalize_output_amount("0.978879 USDC", "1", "usdc")
        assert abs(result - 0.978879) < 0.000001
