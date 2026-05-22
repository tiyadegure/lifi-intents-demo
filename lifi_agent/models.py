"""
LI.FI Intents Agent — Data models, constants, and chain registry.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


# ── Chain registry ──────────────────────────────────────────────────
CHAINS = {
    "ethereum": {"id": "1", "name": "Ethereum"},
    "base": {"id": "8453", "name": "Base"},
    "arbitrum": {"id": "42161", "name": "Arbitrum"},
    "optimism": {"id": "10", "name": "Optimism"},
    "polygon": {"id": "137", "name": "Polygon"},
    "bsc": {"id": "56", "name": "BSC"},
    "avalanche": {"id": "43114", "name": "Avalanche"},
    "zksync": {"id": "324", "name": "zkSync"},
    "linea": {"id": "59144", "name": "Linea"},
    "scroll": {"id": "534352", "name": "Scroll"},
    "blast": {"id": "81457", "name": "Blast"},
    "mantle": {"id": "5000", "name": "Mantle"},
    "sonic": {"id": "146", "name": "Sonic"},
}

CHAIN_ALIASES = {
    "arb": "arbitrum", "arbitrum": "arbitrum",
    "opt": "optimism", "op": "optimism", "optimism": "optimism",
    "poly": "polygon", "polygon": "polygon",
    "eth": "ethereum", "ethereum": "ethereum",
    "base": "base",
    "bsc": "bsc",
    "avax": "avalanche", "avalanche": "avalanche",
    "zksync": "zksync",
    "linea": "linea",
    "scroll": "scroll",
    "blast": "blast",
    "mantle": "mantle",
    "sonic": "sonic",
}

# Common token addresses (USDC on major chains)
TOKENS = {
    "usdc": {
        "1": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "8453": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "42161": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "10": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
        "137": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
        "56": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
    },
    "usdt": {
        "1": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "42161": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
        "10": "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58",
        "137": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "56": "0x55d398326f99059fF775485246999027B3197955",
    },
    "eth": {
        "1": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
        "8453": "0x4200000000000000000000000000000000000006",
        "42161": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "10": "0x4200000000000000000000000000000000000006",
    },
}

# Token decimals for amount conversion
TOKEN_DECIMALS = {
    "usdc": 6,
    "usdt": 6,
    "eth": 18,
    "weth": 18,
}

# Configurable demo address (set DEMO_ADDRESS env var for production)
DEMO_ADDRESS = os.environ.get("DEMO_ADDRESS", "0x0000000000000000000000000000000000000000")


# ── Amount conversion ───────────────────────────────────────────────

def amount_to_raw(human_amount: str, token: str) -> str:
    """Convert human-readable amount to raw amount with proper decimals.

    Example: amount_to_raw("10", "usdc") -> "10000000"
    """
    decimals = TOKEN_DECIMALS.get(token.lower(), 18)
    try:
        amount_float = float(human_amount)
        raw_amount = int(amount_float * (10 ** decimals))
        return str(raw_amount)
    except ValueError:
        return human_amount


def raw_to_amount(raw_amount: str, token: str) -> float:
    """Convert raw amount (from MCP) back to human-readable amount.

    Example: raw_to_amount("9980000", "usdc") -> 9.98
    """
    decimals = TOKEN_DECIMALS.get(token.lower(), 18)
    try:
        cleaned = ''.join(c for c in raw_amount if c.isdigit())
        return int(cleaned) / (10 ** decimals)
    except (ValueError, OverflowError):
        return 0.0


def normalize_output_amount(output_amount: str, input_amount: str, token: str) -> float:
    """Convert output amount to human-readable, handling both raw and human formats.

    If output looks like raw units (>1000x input), converts via raw_to_amount.
    """
    try:
        out_str = ''.join(c for c in output_amount if c.isdigit() or c == '.')
        out_raw = float(out_str)
        inp = float(input_amount)
        if out_raw > inp * 1000:
            return raw_to_amount(output_amount, token)
        return out_raw
    except (ValueError, ZeroDivisionError):
        return 0.0


# ── Intent & Policy dataclasses ────────────────────────────────────

class Intent:
    def __init__(self, from_chain: str, to_chain: str, token: str, amount: str, address: str = DEMO_ADDRESS):
        self.from_chain = from_chain
        self.to_chain = to_chain
        self.token = token.lower()
        self.amount = amount
        self.address = address

    def from_chain_id(self) -> str:
        return CHAINS[self.from_chain]["id"]

    def to_chain_id(self) -> str:
        return CHAINS[self.to_chain]["id"]

    def from_token_address(self) -> str:
        chain_id = self.from_chain_id()
        return TOKENS.get(self.token, {}).get(chain_id, "")

    def to_token_address(self) -> str:
        chain_id = self.to_chain_id()
        return TOKENS.get(self.token, {}).get(chain_id, "")

    def __repr__(self):
        return f"Intent({self.amount} {self.token.upper()} {self.from_chain}→{self.to_chain})"


@dataclass
class Policy:
    """User-defined safety policy for cross-chain intents."""
    max_fee_pct: Optional[float] = None
    require_healthy_route: bool = False
    min_output_amount: Optional[float] = None
    max_slippage: Optional[float] = None
    allow_cross_chain: bool = True
    avoid_chains: List[str] = field(default_factory=list)
    prefer_cheapest: bool = False
    require_quote: bool = True

    def __repr__(self):
        parts = []
        if self.max_fee_pct is not None:
            parts.append(f"fee<{self.max_fee_pct}%")
        if self.require_healthy_route:
            parts.append("healthy route")
        if self.min_output_amount is not None:
            parts.append(f"output>={self.min_output_amount}")
        if self.max_slippage is not None:
            parts.append(f"slippage<{self.max_slippage}%")
        if not self.allow_cross_chain:
            parts.append("no cross-chain")
        if self.avoid_chains:
            parts.append(f"avoid {', '.join(self.avoid_chains)}")
        if self.prefer_cheapest:
            parts.append("prefer cheapest")
        if not self.require_quote:
            parts.append("allow no quote")
        return f"Policy({', '.join(parts) if parts else 'no constraints'})"


@dataclass
class Verdict:
    """Final decision with detailed reasoning."""
    executable: bool
    checks: List[Dict[str, Any]]
    reason: str
    quote_data: Optional[Dict] = None

    def __repr__(self):
        return f"Verdict({'EXECUTABLE' if self.executable else 'REFUSED'})"


@dataclass
class DecisionStep:
    """A single step in the decision trace."""
    name: str
    status: str         # "passed", "failed", "warning", "skipped"
    detail: str
    duration_ms: int = 0
    mcp_tool: str = ""
    mcp_args: Dict[str, Any] = field(default_factory=dict)
    mcp_result: Optional[Dict] = None

    def __repr__(self):
        return f"DecisionStep({self.name}: {self.status})"


@dataclass
class DecisionResult:
    """Complete decision trace with all steps."""
    verdict: str                    # "EXECUTABLE" or "REFUSED"
    reason: str
    steps: List[DecisionStep]
    intent: Optional[Intent] = None
    policy: Optional[Policy] = None
    quote_data: Optional[Dict] = None
    total_duration_ms: int = 0

    def __repr__(self):
        return f"DecisionResult({self.verdict}, {len(self.steps)} steps)"
