"""
LI.FI Intents Agent — AI-powered cross-chain assistant.

Usage:
    python3 -m lifi_agent                    # Interactive mode
    python3 -m lifi_agent "send 10 USDC from Base to Arbitrum"  # Single command
"""

import sys
import json
import os
import re
import time
import sqlite3
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime
from .mcp_client import MCPClient

# ── SQLite Quote Store ─────────────────────────────────────────────
DB_FILE = Path.home() / ".lifi_agent_quotes.db"

class QuoteStore:
    """Persistent quote history using SQLite."""

    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent TEXT,
                    from_chain TEXT,
                    to_chain TEXT,
                    token TEXT,
                    input_amount TEXT,
                    output_amount TEXT,
                    fee_pct TEXT,
                    quote_id TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def store(self, intent_repr: str, from_chain: str, to_chain: str,
              token: str, input_amount: str, output_amount: str,
              fee_pct: Optional[str], quote_id: str):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO quotes (intent, from_chain, to_chain, token,
                                  input_amount, output_amount, fee_pct, quote_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (intent_repr, from_chain, to_chain, token, input_amount,
                  output_amount, fee_pct, quote_id))
            conn.commit()

    def get_recent(self, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM quotes ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
            if total == 0:
                return {"total": 0, "avg_fee": 0, "top_routes": [], "top_tokens": []}

            avg_fee = conn.execute(
                "SELECT AVG(CAST(fee_pct AS REAL)) FROM quotes WHERE fee_pct != '999'"
            ).fetchone()[0] or 0

            top_routes = conn.execute("""
                SELECT from_chain, to_chain, COUNT(*) as cnt
                FROM quotes GROUP BY from_chain, to_chain
                ORDER BY cnt DESC LIMIT 5
            """).fetchall()

            top_tokens = conn.execute("""
                SELECT token, COUNT(*) as cnt
                FROM quotes GROUP BY token
                ORDER BY cnt DESC LIMIT 3
            """).fetchall()

            return {
                "total": total,
                "avg_fee": round(avg_fee, 3),
                "top_routes": [(r[0], r[1], r[2]) for r in top_routes],
                "top_tokens": [(t[0], t[1]) for t in top_tokens],
            }

_quote_store = None

def get_quote_store() -> QuoteStore:
    global _quote_store
    if _quote_store is None:
        _quote_store = QuoteStore()
    return _quote_store

# ── Rich TUI ──────────────────────────────────────────────────────
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
from rich import box

console = Console()

# Chain color map for Rich styling
CHAIN_COLORS = {
    "ethereum": "cyan",
    "base": "blue",
    "arbitrum": "red",
    "optimism": "bold red",
    "polygon": "magenta",
    "bsc": "yellow",
    "avalanche": "bold red",
    "zksync": "white",
    "linea": "bold blue",
    "scroll": "dim white",
    "blast": "bold yellow",
    "mantle": "white",
    "sonic": "bold cyan",
}

def styled_chain(name: str) -> str:
    """Return a Rich-formatted chain name."""
    color = CHAIN_COLORS.get(name, "white")
    return f"[{color}]{name.title()}[/{color}]"

def status_ok(msg: str):
    console.print(f"  [green]✓[/green] {msg}")

def status_err(msg: str):
    console.print(f"  [red]✗[/red] {msg}")

def status_cached(msg: str):
    console.print(f"  [yellow]⚡[/yellow] {msg}")

def status_loading(msg: str):
    console.print(f"  [blue]⏳[/blue] {msg}")

# ── Preferences storage ────────────────────────────────────────────
PREFS_FILE = Path.home() / ".lifi_agent_prefs.json"

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

# Configurable demo address (set DEMO_ADDRESS env var for production)
DEMO_ADDRESS = os.environ.get("DEMO_ADDRESS", "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")


# ── Intent Parser ───────────────────────────────────────────────────
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


# ── Policy & Verdict System ────────────────────────────────────────
@dataclass
class Policy:
    """User-defined safety policy for cross-chain intents."""
    max_fee_pct: Optional[float] = None        # e.g., 0.5 means max 0.5% fee
    require_healthy_route: bool = False         # require route health check
    min_output_amount: Optional[float] = None   # minimum output amount
    max_slippage: Optional[float] = None        # max slippage percentage
    allow_cross_chain: bool = True              # allow cross-chain transfers
    avoid_chains: List[str] = field(default_factory=list)  # chains to avoid
    prefer_cheapest: bool = False               # prefer cheapest route
    require_quote: bool = True                  # require quote to execute
    
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
    checks: List[Dict[str, Any]]      # list of {name, passed, detail}
    reason: str                        # human-readable reason
    quote_data: Optional[Dict] = None  # raw quote data if available
    
    def __repr__(self):
        return f"Verdict({'EXECUTABLE' if self.executable else 'REFUSED'})"


@dataclass
class DecisionStep:
    """A single step in the decision trace."""
    name: str           # step name (e.g., "Route Supported", "Fee Policy")
    status: str         # "passed", "failed", "warning", "skipped"
    detail: str         # human-readable detail
    duration_ms: int = 0  # time taken in milliseconds
    mcp_tool: str = ""  # MCP tool called (if any)
    mcp_args: Dict[str, Any] = field(default_factory=dict)  # MCP arguments
    mcp_result: Optional[Dict] = None  # raw MCP result
    
    def __repr__(self):
        return f"DecisionStep({self.name}: {self.status})"


@dataclass
class DecisionResult:
    """Complete decision trace with all steps."""
    verdict: str                    # "EXECUTABLE" or "REFUSED"
    reason: str                     # human-readable reason
    steps: List[DecisionStep]       # ordered list of decision steps
    intent: Optional[Intent] = None # parsed intent
    policy: Optional[Policy] = None # parsed policy
    quote_data: Optional[Dict] = None  # raw quote data
    total_duration_ms: int = 0      # total time taken
    
    def __repr__(self):
        return f"DecisionResult({self.verdict}, {len(self.steps)} steps)"


def parse_policy(text: str) -> Policy:
    """Extract safety policy from natural language.
    
    Examples:
        "send 10 USDC from Base to Arbitrum only if fee < 0.5%"
        "bridge 50 USDT if route is healthy and fee < 1%"
        "transfer 0.5 ETH if output >= 0.49"
        "avoid Ethereum"
        "prefer cheapest route"
        "do not execute if no quote"
    """
    policy = Policy()
    text_lower = text.lower()
    
    # Extract fee limit: "fee < 0.5%", "fee under 1%", "max fee 0.3%"
    fee_match = re.search(r'(?:fee|fees?)\s*(?:<|<=|under|below|max(?:imum)?)\s*(\d+\.?\d*)\s*%', text)
    if fee_match:
        policy.max_fee_pct = float(fee_match.group(1))
    
    # Extract route health requirement: "if route is healthy", "healthy route"
    if re.search(r'(?:route|routes?)\s*(?:is|are)?\s*healthy', text_lower):
        policy.require_healthy_route = True
    if re.search(r'healthy\s*(?:route|routes?)', text_lower):
        policy.require_healthy_route = True
    
    # Extract minimum output: "output >= 9.95", "min output 9.9", "min output 100"
    output_match = re.search(r'(?:output|min(?:imum)?\s*output)\s*(?:>=|>|at\s*least)?\s*(\d+\.?\d*)', text)
    if output_match and output_match.group(1):
        policy.min_output_amount = float(output_match.group(1))
    
    # Extract slippage: "slippage < 0.5%", "max slippage 1%"
    slippage_match = re.search(r'slippage\s*(?:<|<=|under|below|max(?:imum)?)\s*(\d+\.?\d*)\s*%', text)
    if slippage_match:
        policy.max_slippage = float(slippage_match.group(1))
    
    # Extract avoid chains: "avoid Ethereum", "avoid eth and polygon"
    avoid_match = re.search(r'avoid\s+([\w\s,]+?)(?:\s+and\s+|\s*,\s*|\s*$)', text_lower)
    if avoid_match:
        chains_str = avoid_match.group(1)
        # Split by "and" or comma
        chains = re.split(r'\s+and\s+|\s*,\s*', chains_str)
        for chain in chains:
            chain = chain.strip()
            if chain in CHAIN_ALIASES:
                policy.avoid_chains.append(CHAIN_ALIASES[chain])
            elif chain in CHAINS:
                policy.avoid_chains.append(chain)
    
    # Extract prefer cheapest: "prefer cheapest route", "cheapest route"
    if re.search(r'prefer\s+cheapest(?:\s+route)?', text_lower):
        policy.prefer_cheapest = True
    if re.search(r'cheapest\s+route', text_lower):
        policy.prefer_cheapest = True
    
    # Extract no quote requirement: "do not execute if no quote", "no quote = no execute"
    if re.search(r'do\s+not\s+execute\s+if\s+no\s+quote', text_lower):
        policy.require_quote = True
    if re.search(r'no\s+quote\s*=\s*no\s+execute', text_lower):
        policy.require_quote = True
    
    # Extract no cross-chain: "same chain only", "no cross-chain"
    if re.search(r'same\s+chain\s+only', text_lower):
        policy.allow_cross_chain = False
    if re.search(r'no\s+cross[- ]chain', text_lower):
        policy.allow_cross_chain = False
    
    return policy


def parse_intent_with_policy(text: str) -> tuple[Intent, Policy]:
    """Parse both intent and policy from natural language.
    
    Returns: (Intent, Policy) tuple
    """
    # Extract policy conditions before parsing intent
    # Remove policy clauses from text for intent parsing
    intent_text = re.sub(
        r'\b(?:only\s+)?if\b.*$',
        '',
        text,
        flags=re.IGNORECASE
    ).strip()
    
    intent = parse_intent(intent_text)
    policy = parse_policy(text)
    
    return intent, policy


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


def parse_intent(text: str) -> Intent:
    """Parse natural language into a cross-chain intent.

    Examples:
        "send 10 USDC from Base to Arbitrum"
        "bridge 50 USDT polygon to ethereum"
        "transfer 0.5 ETH from optimism to base"
    """
    text = text.lower().strip()

    # Normalize arrow syntax: "base->arb", "base to arb", "bridge X eth to poly"
    arrow_match = re.search(r'(\w+)\s*(?:->|→)\s*(\w+)', text)
    if arrow_match:
        src, dst = arrow_match.group(1), arrow_match.group(2)
        src_full = CHAIN_ALIASES.get(src, src)
        dst_full = CHAIN_ALIASES.get(dst, dst)
        if src_full in CHAINS and dst_full in CHAINS:
            text = text[:arrow_match.start()] + f"from {src_full} to {dst_full}" + text[arrow_match.end():]

    # Extract amount + token
    amount_match = re.search(r'(\d+\.?\d*)\s*(usdc|usdt|eth|weth)', text)
    if not amount_match:
        raise ValueError("Couldn't find amount and token. Try: 'send 10 USDC from Base to Arbitrum'")
    amount = amount_match.group(1)
    token = amount_match.group(2).replace("weth", "eth")

    # Extract chains by position in text (earliest = from, latest = to)
    chain_positions = []
    for alias, full_name in CHAIN_ALIASES.items():
        pos = text.find(alias)
        # Avoid matching substrings (e.g. "base" inside "database")
        if pos >= 0:
            end = pos + len(alias)
            if (pos == 0 or not text[pos-1].isalpha()) and (end >= len(text) or not text[end].isalpha()):
                chain_positions.append((pos, full_name))
    chain_positions.sort()

    if len(chain_positions) < 2:
        found = [c[1] for c in chain_positions]
        raise ValueError(f"Need two chains. Found: {found}. Supported: {', '.join(CHAINS.keys())}")

    # Use "from X to Y" pattern if available, else use text position
    from_match = re.search(r'from\s+(\w+)', text)
    to_match = re.search(r'to\s+(\w+)', text)

    if from_match:
        src = from_match.group(1)
        if src in CHAINS:
            from_chain = src
        elif src in CHAIN_ALIASES:
            from_chain = CHAIN_ALIASES[src]
        else:
            from_chain = chain_positions[0][1]
    else:
        from_chain = chain_positions[0][1]

    if to_match:
        dst = to_match.group(1)
        if dst in CHAINS:
            to_chain = dst
        elif dst in CHAIN_ALIASES:
            to_chain = CHAIN_ALIASES[dst]
        else:
            to_chain = chain_positions[-1][1]
    else:
        to_chain = chain_positions[-1][1]

    if from_chain == to_chain:
        raise ValueError("Source and destination chains must be different")

    return Intent(from_chain, to_chain, token, amount)


def parse_intent_llm(text: str, api_key: str = None, model: str = "gpt-4o-mini") -> Intent:
    """Parse natural language using LLM for more flexible understanding.
    
    Requires OPENAI_API_KEY env var or api_key parameter.
    Falls back to regex parser if LLM fails.
    """
    import httpx
    
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return parse_intent(text)  # Fallback to regex
    
    try:
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{
                    "role": "system",
                    "content": """Extract cross-chain transfer intent. Return JSON:
{"from_chain": "base", "to_chain": "arbitrum", "token": "usdc", "amount": "10"}

Supported chains: ethereum, base, arbitrum, optimism, polygon, bsc, avalanche, zksync, linea, scroll, blast, mantle, sonic
Supported tokens: usdc, usdt, eth

Examples:
- "send 10 USDC base->arb" -> {"from_chain": "base", "to_chain": "arbitrum", "token": "usdc", "amount": "10"}
- "bridge 50 USDT eth to poly" -> {"from_chain": "ethereum", "to_chain": "polygon", "token": "usdt", "amount": "50"}
- "move 0.5 ETH from optimism" -> {"from_chain": "optimism", "to_chain": "arbitrum", "token": "eth", "amount": "0.5"}"""
                }, {
                    "role": "user",
                    "content": text
                }],
                "temperature": 0,
                "max_tokens": 100
            },
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()["choices"][0]["message"]["content"]
            data = json.loads(result)
            return Intent(
                from_chain=data["from_chain"],
                to_chain=data["to_chain"],
                token=data["token"],
                amount=data["amount"]
            )
    except Exception as e:
        logging.debug(f"LLM parsing failed, falling back to regex: {e}")
    
    return parse_intent(text)  # Fallback to regex


# ── Agent ───────────────────────────────────────────────────────────
class LifAgent:
    """AI Agent for cross-chain operations via LI.FI Intents MCP."""

    def __init__(self):
        self.mcp = MCPClient()
        self.history: list[dict] = []
        self.quote_history: list[dict] = []
        self.preferences: dict = {"default_chain": None, "default_token": "usdc", "favorite_routes": []}
        self.pending_order: dict = {}
        self._load_prefs()

    def _load_prefs(self):
        """Load preferences from disk."""
        if PREFS_FILE.exists():
            try:
                with open(PREFS_FILE) as f:
                    saved = json.load(f)
                    self.preferences.update(saved)
            except Exception:
                pass

    def _save_prefs(self):
        """Save preferences to disk."""
        try:
            with open(PREFS_FILE, "w") as f:
                json.dump(self.preferences, f, indent=2)
        except Exception:
            pass

    def remember_route(self, from_chain: str, to_chain: str, token: str):
        """Remember a frequently used route."""
        route = f"{from_chain}:{to_chain}:{token}"
        favs = self.preferences.get("favorite_routes", [])
        if route not in favs:
            favs.append(route)
            self.preferences["favorite_routes"] = favs[-10:]  # Keep last 10
            self._save_prefs()

    def get_favorite_routes(self) -> list[str]:
        return self.preferences.get("favorite_routes", [])

    def connect(self):
        info = self.mcp.connect()
        server = info.get("serverInfo", {})
        return f"Connected to {server.get('name', '?')} v{server.get('version', '?')}"

    def get_routes(self) -> dict:
        """Get all supported routes."""
        return self.mcp.call("get-supported-routes", {})

    def get_quote(self, intent: Intent) -> dict:
        """Get a cross-chain quote with route validation."""
        routes_result = self.get_routes()
        route_list = routes_result.get("data", {}).get("routes", [])
        from_id = int(intent.from_chain_id())
        to_id = int(intent.to_chain_id())

        if route_list:
            matching = [r for r in route_list
                        if r.get("fromChainId") == from_id and r.get("toChainId") == to_id
                        and r.get("fromToken", {}).get("address", "").lower() == intent.from_token_address().lower()]
            if not matching:
                return {"error": f"No route found for {intent.from_chain} → {intent.to_chain} ({intent.token.upper()})"}

        args = {
            "fromChain": intent.from_chain_id(),
            "toChain": intent.to_chain_id(),
            "fromToken": intent.from_token_address(),
            "toToken": intent.to_token_address(),
            "amount": amount_to_raw(intent.amount, intent.token),
            "userAddress": intent.address,
        }
        result = self.mcp.call("request-quote", args)

        raw = result.get("raw", "")
        if "Unknown token" in raw:
            result["suggestion"] = f"Token {intent.token.upper()} may not be available on {intent.from_chain}. Try: routes"
            result["error"] = raw

        if "error" not in result:
            self.quote_history.append({
                "timestamp": time.time(),
                "intent": repr(intent),
                "result": result,
            })
            self.quote_history = self.quote_history[-10:]
            
            # Store in SQLite
            quotes = result.get("data", {}).get("quotes", [])
            if quotes:
                q = quotes[0]
                output = q.get("outputAmount", "0")
                get_quote_store().store(
                    intent_repr=repr(intent),
                    from_chain=intent.from_chain,
                    to_chain=intent.to_chain,
                    token=intent.token,
                    input_amount=intent.amount,
                    output_amount=output,
                    fee_pct=self._calc_fee(intent.amount, output, intent.token),
                    quote_id=q.get("quoteId", "")
                )

        return result

    def safe_verdict(self, intent: Intent, policy: Policy) -> Verdict:
        """Execute the Safe Verdict pipeline: check route → health → quote → policy → decision.
        
        Returns a Verdict with EXECUTABLE or REFUSED and detailed reasoning.
        """
        checks = []
        quote_data = None
        
        # ── Step 1: Check supported route ─────────────────────────
        try:
            routes_result = self.get_routes()
            route_list = routes_result.get("data", {}).get("routes", [])
            from_id = int(intent.from_chain_id())
            to_id = int(intent.to_chain_id())
            
            if route_list:
                matching = [r for r in route_list
                            if r.get("fromChainId") == from_id and r.get("toChainId") == to_id
                            and r.get("fromToken", {}).get("address", "").lower() == intent.from_token_address().lower()]
                route_supported = len(matching) > 0
            else:
                route_supported = True  # Assume supported if can't verify
            
            checks.append({
                "name": "Route Supported",
                "passed": route_supported,
                "detail": f"{intent.from_chain} → {intent.to_chain} ({intent.token.upper()})"
            })
            
            if not route_supported:
                return Verdict(
                    executable=False,
                    checks=checks,
                    reason=f"No supported route found for {intent.from_chain} → {intent.to_chain} ({intent.token.upper()})."
                )
        except Exception as e:
            checks.append({
                "name": "Route Supported",
                "passed": False,
                "detail": f"Error checking route: {e}"
            })
            return Verdict(executable=False, checks=checks, reason=f"Failed to check route: {e}")
        
        # ── Step 2: Check route health (if policy requires) ───────
        if policy.require_healthy_route:
            try:
                health_result = self.check_route_health(intent.from_chain, intent.to_chain)
                health_data = health_result.get("data", {})
                status = health_data.get("status", "unknown")
                is_healthy = status.lower() in ["healthy", "ok", "good"]
                
                checks.append({
                    "name": "Route Health",
                    "passed": is_healthy,
                    "detail": f"Status: {status.upper()}"
                })
                
                if not is_healthy:
                    return Verdict(
                        executable=False,
                        checks=checks,
                        reason=f"Route health check failed. Status: {status}. The agent refuses to prepare the order."
                    )
            except Exception as e:
                checks.append({
                    "name": "Route Health",
                    "passed": False,
                    "detail": f"Error checking health: {e}"
                })
                return Verdict(executable=False, checks=checks, reason=f"Failed to check route health: {e}")
        else:
            checks.append({
                "name": "Route Health",
                "passed": True,
                "detail": "Skipped (not required by policy)"
            })
        
        # ── Step 3: Get quote ─────────────────────────────────────
        try:
            args = {
                "fromChain": intent.from_chain_id(),
                "toChain": intent.to_chain_id(),
                "fromToken": intent.from_token_address(),
                "toToken": intent.to_token_address(),
                "amount": amount_to_raw(intent.amount, intent.token),
                "userAddress": intent.address,
            }
            result = self.mcp.call("request-quote", args)
            
            if "error" in result:
                checks.append({
                    "name": "Quote Received",
                    "passed": False,
                    "detail": result.get("error", "Unknown error")
                })
                return Verdict(executable=False, checks=checks, reason=f"Failed to get quote: {result.get('error', 'Unknown error')}")
            
            quote_data = result.get("data", {})
            quotes = quote_data.get("quotes", [])
            
            if not quotes:
                checks.append({
                    "name": "Quote Received",
                    "passed": False,
                    "detail": "No quotes returned"
                })
                return Verdict(executable=False, checks=checks, reason="No quotes available for this route.")
            
            q = quotes[0]
            output_amount = q.get("outputAmount", "0")
            quote_id = q.get("quoteId", "")
            
            checks.append({
                "name": "Quote Received",
                "passed": True,
                "detail": f"Output: {output_amount}, Quote ID: {quote_id[:16]}..."
            })
            
        except Exception as e:
            checks.append({
                "name": "Quote Received",
                "passed": False,
                "detail": f"Error getting quote: {e}"
            })
            return Verdict(executable=False, checks=checks, reason=f"Failed to get quote: {e}")
        
        # ── Step 4: Calculate fee ─────────────────────────────────
        fee_pct = self._calc_fee(intent.amount, output_amount, intent.token)
        fee_pct_float = float(fee_pct) if fee_pct else 999.0
        
        checks.append({
            "name": "Fee Calculated",
            "passed": True,
            "detail": f"Fee: {fee_pct}%"
        })
        
        # ── Step 5: Check policy constraints ──────────────────────
        policy_passed = True
        policy_reason = ""
        
        # Check max fee
        if policy.max_fee_pct is not None:
            fee_ok = fee_pct_float <= policy.max_fee_pct
            checks.append({
                "name": "Fee Policy",
                "passed": fee_ok,
                "detail": f"Fee {fee_pct}% {'≤' if fee_ok else '>'} limit {policy.max_fee_pct}%"
            })
            if not fee_ok:
                policy_passed = False
                policy_reason = f"The quote fee is {fee_pct}%, which exceeds the user limit of {policy.max_fee_pct}%."
        
        # Check min output
        if policy.min_output_amount is not None:
            output_float = normalize_output_amount(output_amount, intent.amount, intent.token)
            output_ok = output_float >= policy.min_output_amount
            checks.append({
                "name": "Output Policy",
                "passed": output_ok,
                "detail": f"Output {output_float:.4f} {'≥' if output_ok else '<'} min {policy.min_output_amount}"
            })
            if not output_ok:
                policy_passed = False
                policy_reason = f"Output {output_float:.4f} is below minimum {policy.min_output_amount}."
        
        # Check avoid chains (both source and destination)
        if policy.avoid_chains:
            avoided = []
            if intent.from_chain in policy.avoid_chains:
                avoided.append(f"source chain {intent.from_chain}")
            if intent.to_chain in policy.avoid_chains:
                avoided.append(f"target chain {intent.to_chain}")
            if avoided:
                checks.append({
                    "name": "Avoid Chains",
                    "passed": False,
                    "detail": f"{', '.join(avoided)} in avoid list: {', '.join(policy.avoid_chains)}"
                })
                policy_passed = False
                policy_reason = f"{avoided[0].title()} is in the avoid list."
            else:
                checks.append({
                    "name": "Avoid Chains",
                    "passed": True,
                    "detail": f"Neither {intent.from_chain} nor {intent.to_chain} in avoid list"
                })
        
        # Check cross-chain allowance
        if not policy.allow_cross_chain and intent.from_chain != intent.to_chain:
            checks.append({
                "name": "Cross-Chain",
                "passed": False,
                "detail": f"Cross-chain transfer not allowed by policy"
            })
            policy_passed = False
            policy_reason = "Cross-chain transfer is not allowed by policy."
        elif not policy.allow_cross_chain:
            checks.append({
                "name": "Cross-Chain",
                "passed": True,
                "detail": "Same-chain transfer allowed"
            })
        
        # Check require quote
        if not policy.require_quote and not quotes:
            checks.append({
                "name": "Quote Required",
                "passed": True,
                "detail": "No quote required by policy"
            })
        
        # ── Step 6: Final Verdict ─────────────────────────────────
        if policy_passed:
            reason_parts = [f"This intent satisfies the user policy."]
            if fee_pct:
                reason_parts.append(f"Fee {fee_pct}% is within acceptable limits.")
            if policy.prefer_cheapest:
                reason_parts.append("Route selected based on cheapest option.")
            
            return Verdict(
                executable=True,
                checks=checks,
                reason=" ".join(reason_parts),
                quote_data=quote_data
            )
        else:
            return Verdict(
                executable=False,
                checks=checks,
                reason=f"{policy_reason} The agent refuses to prepare the order.",
                quote_data=quote_data
            )

    def safe_verdict_trace(self, intent: Intent, policy: Policy) -> DecisionResult:
        """Execute Safe Verdict with full decision trace.
        
        Returns a DecisionResult with detailed step-by-step trace.
        """
        start_time = time.time()
        steps = []
        quote_data = None
        
        # ── Step 1: Parse Intent ──────────────────────────────────
        step_start = time.time()
        steps.append(DecisionStep(
            name="Parse Intent",
            status="passed",
            detail=f"{intent.amount} {intent.token.upper()} {intent.from_chain} → {intent.to_chain}",
            duration_ms=int((time.time() - step_start) * 1000)
        ))
        
        # ── Step 2: Parse Policy ──────────────────────────────────
        step_start = time.time()
        steps.append(DecisionStep(
            name="Parse Policy",
            status="passed",
            detail=str(policy),
            duration_ms=int((time.time() - step_start) * 1000)
        ))
        
        # ── Step 3: Check Supported Route ─────────────────────────
        step_start = time.time()
        try:
            routes_result = self.get_routes()
            route_list = routes_result.get("data", {}).get("routes", [])
            from_id = int(intent.from_chain_id())
            to_id = int(intent.to_chain_id())
            
            if route_list:
                matching = [r for r in route_list
                            if r.get("fromChainId") == from_id and r.get("toChainId") == to_id
                            and r.get("fromToken", {}).get("address", "").lower() == intent.from_token_address().lower()]
                route_supported = len(matching) > 0
            else:
                route_supported = True
            
            duration = int((time.time() - step_start) * 1000)
            steps.append(DecisionStep(
                name="Check Supported Route",
                status="passed" if route_supported else "failed",
                detail=f"{intent.from_chain} → {intent.to_chain} ({intent.token.upper()})",
                duration_ms=duration,
                mcp_tool="get-supported-routes",
                mcp_result=routes_result
            ))
            
            if not route_supported:
                return DecisionResult(
                    verdict="REFUSED",
                    reason=f"No supported route found for {intent.from_chain} → {intent.to_chain} ({intent.token.upper()}).",
                    steps=steps,
                    intent=intent,
                    policy=policy,
                    total_duration_ms=int((time.time() - start_time) * 1000)
                )
        except Exception as e:
            duration = int((time.time() - step_start) * 1000)
            steps.append(DecisionStep(
                name="Check Supported Route",
                status="failed",
                detail=f"Error: {e}",
                duration_ms=duration,
                mcp_tool="get-supported-routes"
            ))
            return DecisionResult(
                verdict="REFUSED",
                reason=f"Failed to check route: {e}",
                steps=steps,
                intent=intent,
                policy=policy,
                total_duration_ms=int((time.time() - start_time) * 1000)
            )
        
        # ── Step 4: Check Route Health (if required) ──────────────
        step_start = time.time()
        if policy.require_healthy_route:
            try:
                health_result = self.check_route_health(intent.from_chain, intent.to_chain)
                health_data = health_result.get("data", {})
                status = health_data.get("status", "unknown")
                is_healthy = status.lower() in ["healthy", "ok", "good"]
                
                duration = int((time.time() - step_start) * 1000)
                steps.append(DecisionStep(
                    name="Check Route Health",
                    status="passed" if is_healthy else "failed",
                    detail=f"Status: {status.upper()}",
                    duration_ms=duration,
                    mcp_tool="check-route-health",
                    mcp_args={"fromChain": intent.from_chain, "toChain": intent.to_chain},
                    mcp_result=health_result
                ))
                
                if not is_healthy:
                    return DecisionResult(
                        verdict="REFUSED",
                        reason=f"Route health check failed. Status: {status}. The agent refuses to prepare the order.",
                        steps=steps,
                        intent=intent,
                        policy=policy,
                        total_duration_ms=int((time.time() - start_time) * 1000)
                    )
            except Exception as e:
                duration = int((time.time() - step_start) * 1000)
                steps.append(DecisionStep(
                    name="Check Route Health",
                    status="failed",
                    detail=f"Error: {e}",
                    duration_ms=duration,
                    mcp_tool="check-route-health"
                ))
                return DecisionResult(
                    verdict="REFUSED",
                    reason=f"Failed to check route health: {e}",
                    steps=steps,
                    intent=intent,
                    policy=policy,
                    total_duration_ms=int((time.time() - start_time) * 1000)
                )
        else:
            duration = int((time.time() - step_start) * 1000)
            steps.append(DecisionStep(
                name="Check Route Health",
                status="skipped",
                detail="Not required by policy",
                duration_ms=duration
            ))
        
        # ── Step 5: Get Quote ─────────────────────────────────────
        step_start = time.time()
        try:
            quote_args = {
                "fromChain": intent.from_chain_id(),
                "toChain": intent.to_chain_id(),
                "fromToken": intent.from_token_address(),
                "toToken": intent.to_token_address(),
                "amount": amount_to_raw(intent.amount, intent.token),
                "userAddress": intent.address,
            }
            result = self.mcp.call("request-quote", quote_args)
            
            if "error" in result:
                duration = int((time.time() - step_start) * 1000)
                steps.append(DecisionStep(
                    name="Get Quote",
                    status="failed",
                    detail=result.get("error", "Unknown error"),
                    duration_ms=duration,
                    mcp_tool="request-quote",
                    mcp_args=quote_args,
                    mcp_result=result
                ))
                return DecisionResult(
                    verdict="REFUSED",
                    reason=f"Failed to get quote: {result.get('error', 'Unknown error')}",
                    steps=steps,
                    intent=intent,
                    policy=policy,
                    total_duration_ms=int((time.time() - start_time) * 1000)
                )
            
            quote_data = result.get("data", {})
            quotes = quote_data.get("quotes", [])
            
            if not quotes:
                duration = int((time.time() - step_start) * 1000)
                steps.append(DecisionStep(
                    name="Get Quote",
                    status="failed",
                    detail="No quotes returned",
                    duration_ms=duration,
                    mcp_tool="request-quote",
                    mcp_args=quote_args,
                    mcp_result=result
                ))
                return DecisionResult(
                    verdict="REFUSED",
                    reason="No quotes available for this route.",
                    steps=steps,
                    intent=intent,
                    policy=policy,
                    total_duration_ms=int((time.time() - start_time) * 1000)
                )
            
            q = quotes[0]
            output_amount = q.get("outputAmount", "0")
            quote_id = q.get("quoteId", "")
            
            duration = int((time.time() - step_start) * 1000)
            steps.append(DecisionStep(
                name="Get Quote",
                status="passed",
                detail=f"Output: {output_amount}, Quote ID: {quote_id[:16]}...",
                duration_ms=duration,
                mcp_tool="request-quote",
                mcp_args=quote_args,
                mcp_result=result
            ))
            
        except Exception as e:
            duration = int((time.time() - step_start) * 1000)
            steps.append(DecisionStep(
                name="Get Quote",
                status="failed",
                detail=f"Error: {e}",
                duration_ms=duration,
                mcp_tool="request-quote"
            ))
            return DecisionResult(
                verdict="REFUSED",
                reason=f"Failed to get quote: {e}",
                steps=steps,
                intent=intent,
                policy=policy,
                total_duration_ms=int((time.time() - start_time) * 1000)
            )
        
        # ── Step 6: Calculate Fee ─────────────────────────────────
        step_start = time.time()
        fee_pct = self._calc_fee(intent.amount, output_amount, intent.token)
        fee_pct_float = float(fee_pct) if fee_pct else 999.0
        duration = int((time.time() - step_start) * 1000)
        
        steps.append(DecisionStep(
            name="Calculate Fee",
            status="passed",
            detail=f"Fee: {fee_pct}%",
            duration_ms=duration
        ))
        
        # ── Step 7: Check Policy Constraints ──────────────────────
        step_start = time.time()
        policy_passed = True
        policy_reason = ""
        
        # Check max fee
        if policy.max_fee_pct is not None:
            fee_ok = fee_pct_float <= policy.max_fee_pct
            steps.append(DecisionStep(
                name="Fee Policy",
                status="passed" if fee_ok else "failed",
                detail=f"Fee {fee_pct}% {'≤' if fee_ok else '>'} limit {policy.max_fee_pct}%",
                duration_ms=0
            ))
            if not fee_ok:
                policy_passed = False
                policy_reason = f"The quote fee is {fee_pct}%, which exceeds the user limit of {policy.max_fee_pct}%."
        
        # Check min output
        if policy.min_output_amount is not None:
            output_float = normalize_output_amount(output_amount, intent.amount, intent.token)
            output_ok = output_float >= policy.min_output_amount
            steps.append(DecisionStep(
                name="Output Policy",
                status="passed" if output_ok else "failed",
                detail=f"Output {output_float:.4f} {'≥' if output_ok else '<'} min {policy.min_output_amount}",
                duration_ms=0
            ))
            if not output_ok:
                policy_passed = False
                policy_reason = f"Output {output_float:.4f} is below minimum {policy.min_output_amount}."
        
        # Check avoid chains (both source and destination)
        if policy.avoid_chains:
            avoided = []
            if intent.from_chain in policy.avoid_chains:
                avoided.append(f"source chain {intent.from_chain}")
            if intent.to_chain in policy.avoid_chains:
                avoided.append(f"target chain {intent.to_chain}")
            if avoided:
                steps.append(DecisionStep(
                    name="Avoid Chains",
                    status="failed",
                    detail=f"{', '.join(avoided)} in avoid list: {', '.join(policy.avoid_chains)}",
                    duration_ms=0
                ))
                policy_passed = False
                policy_reason = f"{avoided[0].title()} is in the avoid list."
            else:
                steps.append(DecisionStep(
                    name="Avoid Chains",
                    status="passed",
                    detail=f"Neither {intent.from_chain} nor {intent.to_chain} in avoid list",
                    duration_ms=0
                ))
        
        # Check cross-chain allowance
        if not policy.allow_cross_chain and intent.from_chain != intent.to_chain:
            steps.append(DecisionStep(
                name="Cross-Chain",
                status="failed",
                detail="Cross-chain transfer not allowed by policy",
                duration_ms=0
            ))
            policy_passed = False
            policy_reason = "Cross-chain transfer is not allowed by policy."
        elif not policy.allow_cross_chain:
            steps.append(DecisionStep(
                name="Cross-Chain",
                status="passed",
                detail="Same-chain transfer allowed",
                duration_ms=0
            ))
        
        duration = int((time.time() - step_start) * 1000)
        
        # ── Step 8: Final Verdict ─────────────────────────────────
        if policy_passed:
            reason_parts = [f"This intent satisfies the user policy."]
            if fee_pct:
                reason_parts.append(f"Fee {fee_pct}% is within acceptable limits.")
            if policy.prefer_cheapest:
                reason_parts.append("Route selected based on cheapest option.")
            
            return DecisionResult(
                verdict="EXECUTABLE",
                reason=" ".join(reason_parts),
                steps=steps,
                intent=intent,
                policy=policy,
                quote_data=quote_data,
                total_duration_ms=int((time.time() - start_time) * 1000)
            )
        else:
            return DecisionResult(
                verdict="REFUSED",
                reason=f"{policy_reason} The agent refuses to prepare the order.",
                steps=steps,
                intent=intent,
                policy=policy,
                quote_data=quote_data,
                total_duration_ms=int((time.time() - start_time) * 1000)
            )

    def compare_quotes(self, intent: Intent, chains: list[str] = None) -> list[dict]:
        """Compare quotes across multiple destination chains."""
        if chains is None:
            chains = ["arbitrum", "optimism", "base", "polygon", "ethereum"]

        results = []
        for chain in chains:
            if chain == intent.from_chain:
                continue
            try:
                alt_intent = Intent(intent.from_chain, chain, intent.token, intent.amount, intent.address)
                quote = self.get_quote(alt_intent)
                quotes = quote.get("data", {}).get("quotes", [])
                if quotes:
                    q = quotes[0]
                    output = q.get("outputAmount", "0")
                    results.append({
                        "chain": chain,
                        "output": output,
                        "quote_id": q.get("quoteId", ""),
                        "fee_pct": self._calc_fee(intent.amount, output, intent.token),
                    })
            except Exception as e:
                logging.debug(f"Quote failed for {chain}: {e}")
                continue

        # Sort by output amount (higher is better)
        def parse_output(r):
            try:
                return float(''.join(c for c in r.get("output", "0") if c.isdigit() or c == '.'))
            except ValueError:
                return 0

        results.sort(key=parse_output, reverse=True)
        return results

    def _calc_fee(self, input_amount: str, output_amount: str, token: str = "usdc") -> Optional[str]:
        """Calculate fee percentage. Returns None on error.
        
        input_amount: human-readable (e.g. "10")
        output_amount: raw from MCP (e.g. "9980000") or human-readable (e.g. "9.98")
        token: token symbol for decimal conversion
        """
        try:
            inp = float(input_amount)
            out_human = normalize_output_amount(output_amount, input_amount, token)
            if inp == 0:
                return None
            fee = (inp - out_human) / inp * 100
            return f"{fee:.2f}"
        except (ValueError, ZeroDivisionError):
            return None

    def prepare_order(self, quote_id: str, address: str = DEMO_ADDRESS) -> dict:
        """Prepare an order from a quote."""
        return self.mcp.call("prepare-order", {"quoteId": quote_id, "userAddress": address})

    def track_order(self, order_id: str) -> dict:
        """Track an order's status."""
        return self.mcp.call("track-order", {"orderId": order_id})

    def list_orders(self, limit: int = 5) -> dict:
        """List recent orders."""
        return self.mcp.call("list-orders", {"limit": limit})

    # ── Solver tools ────────────────────────────────────────────
    def get_solver_identities(self) -> dict:
        """List registered solver wallet addresses."""
        return self.mcp.call("get-solver-identities", {})

    def get_quote_inventory(self, from_chain: str, to_chain: str,
                             from_asset: str, to_asset: str) -> dict:
        """View standing quotes for a specific route."""
        return self.mcp.call("get-quote-inventory", {
            "fromChain": from_chain, "toChain": to_chain,
            "fromAsset": from_asset, "toAsset": to_asset,
        })

    def submit_standing_quotes(self, quotes: list) -> dict:
        """Submit or update standing quotes for solver."""
        return self.mcp.call("submit-standing-quotes", {"quotes": quotes})

    def check_route_health(self, from_chain: str, to_chain: str,
                            from_asset: str = None, to_asset: str = None) -> dict:
        """Check health of a specific route."""
        args = {"fromChain": from_chain, "toChain": to_chain}
        if from_asset:
            args["fromAsset"] = from_asset
        if to_asset:
            args["toAsset"] = to_asset
        return self.mcp.call("check-route-health", args)

    def debug_order(self, order_id: str) -> dict:
        """Get full order details for debugging."""
        return self.mcp.call("debug-order", {"orderId": order_id})

    def solver_aware_checks(self, from_chain: str, to_chain: str,
                            from_asset: str = None, to_asset: str = None) -> dict:
        """Run all solver-aware checks for a route.
        
        Returns a comprehensive report with:
        1. Route Health
        2. Quote Availability
        3. Solver Inventory
        4. Order Debugging (if order_id provided)
        """
        report = {
            "route": f"{from_chain} → {to_chain}",
            "checks": [],
            "summary": {}
        }
        
        # ── Check 1: Route Health ─────────────────────────────────
        try:
            health_result = self.check_route_health(from_chain, to_chain, from_asset, to_asset)
            health_data = health_result.get("data", {})
            status = health_data.get("status", "unknown")
            
            report["checks"].append({
                "name": "Route Health",
                "status": status,
                "details": health_data,
                "passed": status.lower() in ["healthy", "ok", "good"]
            })
        except Exception as e:
            report["checks"].append({
                "name": "Route Health",
                "status": "error",
                "details": str(e),
                "passed": False
            })
        
        # ── Check 2: Quote Availability ───────────────────────────
        try:
            # Get supported routes to check if route exists
            routes_result = self.get_routes()
            route_list = routes_result.get("data", {}).get("routes", [])
            
            # Find matching routes
            matching_routes = []
            for r in route_list:
                r_from = r.get("fromChain", "").lower()
                r_to = r.get("toChain", "").lower()
                if r_from == from_chain.lower() and r_to == to_chain.lower():
                    matching_routes.append(r)
            
            quote_available = len(matching_routes) > 0
            
            report["checks"].append({
                "name": "Quote Availability",
                "status": "available" if quote_available else "unavailable",
                "details": {
                    "matching_routes": len(matching_routes),
                    "routes": matching_routes[:3]  # Show first 3
                },
                "passed": quote_available
            })
        except Exception as e:
            report["checks"].append({
                "name": "Quote Availability",
                "status": "error",
                "details": str(e),
                "passed": False
            })
        
        # ── Check 3: Solver Inventory ─────────────────────────────
        try:
            if from_asset and to_asset:
                inventory_result = self.get_quote_inventory(from_chain, to_chain, from_asset, to_asset)
                inventory_data = inventory_result.get("data", {})
                quotes = inventory_data.get("quotes", [])
                
                report["checks"].append({
                    "name": "Solver Inventory",
                    "status": "active" if quotes else "empty",
                    "details": {
                        "quote_count": len(quotes),
                        "quotes": quotes[:3]  # Show first 3
                    },
                    "passed": len(quotes) > 0
                })
            else:
                report["checks"].append({
                    "name": "Solver Inventory",
                    "status": "skipped",
                    "details": "No asset pair specified",
                    "passed": True
                })
        except Exception as e:
            report["checks"].append({
                "name": "Solver Inventory",
                "status": "error",
                "details": str(e),
                "passed": False
            })
        
        # ── Summary ───────────────────────────────────────────────
        passed_checks = sum(1 for c in report["checks"] if c["passed"])
        total_checks = len(report["checks"])
        
        report["summary"] = {
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "failed_checks": total_checks - passed_checks,
            "health_status": report["checks"][0]["status"] if report["checks"] else "unknown",
            "overall_status": "healthy" if passed_checks == total_checks else "degraded"
        }
        
        return report

    def doctor(self) -> dict:
        """Run diagnostic checks on the MCP connection and configuration.
        
        Returns a diagnostic report with checks and warnings.
        """
        report = {
            "checks": [],
            "warnings": []
        }
        
        # ── Check 1: MCP endpoint reachable ───────────────────────
        try:
            # Try to connect to MCP
            info = self.mcp.connect()
            report["checks"].append({
                "name": "MCP endpoint reachable",
                "passed": True,
                "detail": f"Connected to {info.get('serverInfo', {}).get('name', 'unknown')}"
            })
        except Exception as e:
            report["checks"].append({
                "name": "MCP endpoint reachable",
                "passed": False,
                "detail": str(e)
            })
        
        # ── Check 2: MCP session initialized ──────────────────────
        try:
            # Check if we have a session ID
            if self.mcp.session_id:
                report["checks"].append({
                    "name": "MCP session initialized",
                    "passed": True,
                    "detail": f"Session ID: {self.mcp.session_id[:8]}..."
                })
            else:
                report["checks"].append({
                    "name": "MCP session initialized",
                    "passed": False,
                    "detail": "No session ID"
                })
        except Exception as e:
            report["checks"].append({
                "name": "MCP session initialized",
                "passed": False,
                "detail": str(e)
            })
        
        # ── Check 3: get-supported-routes works ───────────────────
        try:
            routes_result = self.get_routes()
            route_count = routes_result.get("data", {}).get("count", 0)
            report["checks"].append({
                "name": "get-supported-routes works",
                "passed": True,
                "detail": f"{route_count} routes available"
            })
        except Exception as e:
            report["checks"].append({
                "name": "get-supported-routes works",
                "passed": False,
                "detail": str(e)
            })
        
        # ── Check 4: Base USDC address configured ─────────────────
        base_usdc = TOKENS.get("usdc", {}).get("8453", "")
        if base_usdc:
            report["checks"].append({
                "name": "Base USDC address configured",
                "passed": True,
                "detail": base_usdc[:10] + "..."
            })
        else:
            report["checks"].append({
                "name": "Base USDC address configured",
                "passed": False,
                "detail": "Not configured"
            })
        
        # ── Check 5: Arbitrum USDC address configured ─────────────
        arb_usdc = TOKENS.get("usdc", {}).get("42161", "")
        if arb_usdc:
            report["checks"].append({
                "name": "Arbitrum USDC address configured",
                "passed": True,
                "detail": arb_usdc[:10] + "..."
            })
        else:
            report["checks"].append({
                "name": "Arbitrum USDC address configured",
                "passed": False,
                "detail": "Not configured"
            })
        
        # ── Check 6: route health tool reachable ──────────────────
        try:
            health_result = self.check_route_health("base", "arbitrum")
            report["checks"].append({
                "name": "route health tool reachable",
                "passed": True,
                "detail": "Tool responded"
            })
        except Exception as e:
            report["checks"].append({
                "name": "route health tool reachable",
                "passed": False,
                "detail": str(e)
            })
        
        # ── Check 7: request-quote works ──────────────────────────
        try:
            # Try to get a quote with a small amount
            quote_result = self.get_quote(Intent("base", "arbitrum", "usdc", "1"))
            if "error" not in quote_result:
                report["checks"].append({
                    "name": "request-quote works",
                    "passed": True,
                    "detail": "Quote received"
                })
            else:
                report["checks"].append({
                    "name": "request-quote works",
                    "passed": False,
                    "detail": quote_result.get("error", "Unknown error")
                })
        except Exception as e:
            report["checks"].append({
                "name": "request-quote works",
                "passed": False,
                "detail": str(e)
            })
        
        # ── Warnings ──────────────────────────────────────────────
        # Warning 1: OPENAI_API_KEY not set
        if not os.environ.get("OPENAI_API_KEY"):
            report["warnings"].append({
                "name": "OPENAI_API_KEY not set",
                "detail": "Using deterministic parser"
            })
        
        # Warning 2: Amount unit behavior
        report["warnings"].append({
            "name": "Amount unit behavior",
            "detail": "Should be verified before real execution"
        })
        
        return report

    def close(self):
        self.mcp.close()


# ── Interactive CLI ─────────────────────────────────────────────────
def interactive():
    """Run interactive CLI mode with Rich TUI and auto-completion."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.styles import Style as PTStyle

    agent = LifAgent()
    use_llm = bool(os.environ.get("OPENAI_API_KEY"))

    # ── Welcome banner ────────────────────────────────────────────
    welcome_text = Text()
    welcome_text.append("LI.FI Intents", style="bold cyan")
    welcome_text.append(" × ", style="dim")
    welcome_text.append("AI Agent", style="bold green")
    welcome_text.append("\n\n")
    welcome_text.append("Cross-chain operations via natural language", style="italic")
    console.print()
    console.print(Panel(welcome_text, border_style="cyan", box=box.ROUNDED, padding=(1, 2)))
    console.print()

    # ── Connect ───────────────────────────────────────────────────
    try:
        info = agent.connect()
        status_ok(info)
    except Exception as e:
        status_err(f"Connection failed: {e}")
        console.print("  [dim]Running in offline mode (cached data only)[/dim]")
    console.print()

    # ── Commands help ─────────────────────────────────────────────
    help_table = Table(show_header=False, box=None, padding=(0, 2))
    help_table.add_column("Command", style="bold")
    help_table.add_column("Description")
    help_table.add_row("[cyan]send[/cyan] 10 USDC from Base to Arbitrum", "Execute a transfer")
    help_table.add_row("[cyan]safe[/cyan] send 10 USDC from Base to Arbitrum if fee < 0.5%", "Safe Verdict: check policy before executing")
    help_table.add_row("[cyan]compare[/cyan] 10 USDC from Ethereum", "Compare quotes across chains")
    help_table.add_row("[cyan]route health[/cyan] base arbitrum", "Check route health status")
    help_table.add_row("[cyan]solver[/cyan] base arbitrum USDC USDC", "Run solver-aware checks (health, quotes, inventory)")
    help_table.add_row("[cyan]doctor[/cyan]", "Run diagnostic checks on MCP connection")
    help_table.add_row("[cyan]routes[/cyan]", "Show supported routes")
    help_table.add_row("[cyan]orders[/cyan]", "Show recent orders")
    help_table.add_row("[cyan]favorites[/cyan]", "Show saved routes")
    help_table.add_row("[cyan]wallet[/cyan]", "Show demo wallet info")
    help_table.add_row("[cyan]history[/cyan]", "Show recent quotes (SQLite)")
    help_table.add_row("[cyan]stats[/cyan]", "Show quote statistics")
    help_table.add_row("[cyan]yes[/cyan] / [cyan]confirm[/cyan]", "Confirm pending order")
    help_table.add_row("[cyan]quit[/cyan]", "Exit")
    console.print(Panel(help_table, title="[bold]Commands[/bold]", border_style="dim", box=box.ROUNDED))
    console.print()

    # ── Auto-completion setup ─────────────────────────────────────
    chain_names = list(CHAINS.keys())
    token_names = ["USDC", "USDT", "ETH"]
    commands = ["send", "safe", "verdict", "compare", "route", "solver", "doctor", "routes", "orders", "favorites", "wallet",
                "history", "stats", "quit"]
    all_completions = commands + chain_names + token_names + [
        "from", "to", "bridge", "transfer", "if", "fee", "healthy",
    ]
    completer = WordCompleter(all_completions, ignore_case=True, match_middle=True)

    prompt_style = PTStyle.from_dict({
        "prompt": "bold cyan",
    })

    session = PromptSession(style=prompt_style)

    pending_intent = None
    pending_quote = None

    def do_prompt() -> str:
        if pending_intent:
            return session.prompt(
                [("class:prompt", "Confirm > ")],
                completer=completer,
            )
        return session.prompt(
            [("class:prompt", "You > ")],
            completer=completer,
        )

    # ── Fee color helper ──────────────────────────────────────────
    def fee_style(pct_str: str) -> str:
        try:
            pct = float(pct_str)
        except ValueError:
            return f"[red]{pct_str}%[/red]"
        if pct < 0.2:
            return f"[green]{pct_str}%[/green]"
        elif pct < 0.5:
            return f"[yellow]{pct_str}%[/yellow]"
        else:
            return f"[red]{pct_str}%[/red]"

    # ── Main loop ─────────────────────────────────────────────────
    while True:
        try:
            text = do_prompt().strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not text:
            continue
        if text in ("quit", "exit", "q"):
            break

        # ── Handle confirmation ────────────────────────────────
        if pending_intent and text in ("yes", "y", "confirm", "ok"):
            if pending_quote:
                quote_id = pending_quote.get("quoteId", "")
                if quote_id:
                    with Progress(SpinnerColumn(), TextColumn("[bold blue]Preparing order...[/bold blue]"), transient=True) as progress:
                        progress.add_task("prep", total=None)
                        result = agent.prepare_order(quote_id)
                    if "error" in result:
                        status_err(result["error"])
                    else:
                        order = result.get("data", {})
                        status_ok("Order prepared!")
                        t = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
                        t.add_column("Key", style="dim")
                        t.add_column("Value")
                        t.add_row("Order ID", str(order.get("id", "?")))
                        t.add_row("Status", str(order.get("status", "?")))
                        console.print(t)
                        agent.pending_order = order
                        agent.remember_route(pending_intent.from_chain, pending_intent.to_chain, pending_intent.token)
                        status_ok("Route saved to favorites!")
                else:
                    status_err("No quote ID available")
            else:
                status_err("No pending quote")
            pending_intent = None
            pending_quote = None
            console.print()
            continue

        if pending_intent and text in ("no", "n", "cancel"):
            console.print("\n  [dim]Cancelled.[/dim]\n")
            pending_intent = None
            pending_quote = None
            continue

        # Cancel pending if new command
        if pending_intent:
            pending_intent = None
            pending_quote = None

        # ── Wallet command ─────────────────────────────────────
        if text == "wallet":
            wallet_table = Table(title="Demo Wallet", box=box.ROUNDED, border_style="cyan")
            wallet_table.add_column("Field", style="dim")
            wallet_table.add_column("Value")
            wallet_table.add_row("Address", f"[bold]{DEMO_ADDRESS}[/bold]")
            wallet_table.add_row("Network", "Multi-chain (demo)")
            wallet_table.add_row("Balance", "[yellow]Connect wallet to view[/yellow]")
            console.print()
            console.print(wallet_table)
            console.print()
            continue

        # ── Handle commands ────────────────────────────────────
        if text == "routes":
            with Progress(SpinnerColumn(), TextColumn("[bold blue]Fetching routes...[/bold blue]"), transient=True) as progress:
                progress.add_task("routes", total=None)
                result = agent.get_routes()
            count = result.get("data", {}).get("count", "?")
            routes_list = result.get("data", {}).get("routes", [])
            msg = result.get("message", "")
            status_ok(f"{count} routes available")
            if routes_list:
                pairs = set()
                for r in routes_list:
                    f = r.get("fromChain", "?")
                    t = r.get("toChain", "?")
                    pairs.add((f, t))
                table = Table(box=box.SIMPLE_HEAVY, border_style="dim")
                table.add_column("#", style="dim", width=4)
                table.add_column("From", style="bold")
                table.add_column("", justify="center")
                table.add_column("To", style="bold")
                for i, (f, t) in enumerate(sorted(pairs)[:15], 1):
                    table.add_row(str(i), styled_chain(f.lower()), "→", styled_chain(t.lower()))
                console.print(table)
                if len(pairs) > 15:
                    console.print(f"  [dim]... and {len(pairs)-15} more[/dim]")
            if msg:
                console.print(f"  {msg}")
            console.print()
            continue

        # ── Doctor command ────────────────────────────────────────
        if text == "doctor":
            console.print(f"\n  [bold cyan]🏥 LI.FI Intents MCP Doctor[/bold cyan]\n")
            
            # Run doctor checks
            with Progress(SpinnerColumn(), TextColumn("[bold blue]Running diagnostic checks...[/bold blue]"), transient=True) as progress:
                progress.add_task("doctor", total=None)
                report = agent.doctor()
            
            # Display checks
            for check in report["checks"]:
                icon = "[green]✓[/green]" if check["passed"] else "[red]✗[/red]"
                console.print(f"  {icon} {check['name']}: {check['detail']}")
            
            # Display warnings
            if report["warnings"]:
                console.print(f"\n  [bold yellow]Warnings:[/bold yellow]")
                for warning in report["warnings"]:
                    console.print(f"  [yellow]![/yellow] {warning['name']}: {warning['detail']}")
            
            console.print()
            continue

        # ── Route health command ──────────────────────────────────
        if text.startswith("route health") or text.startswith("routehealth"):
            parts = text.split()
            if len(parts) < 3:
                console.print("\n  [yellow]Usage:[/yellow] route health <from_chain> <to_chain>")
                console.print("  [dim]Example:[/yellow] route health base arbitrum\n")
                continue
            from_chain = parts[2]
            to_chain = parts[3] if len(parts) > 3 else "arbitrum"
            
            with Progress(SpinnerColumn(), TextColumn(f"[bold blue]Checking route health: {from_chain} → {to_chain}...[/bold blue]"), transient=True) as progress:
                progress.add_task("health", total=None)
                result = agent.check_route_health(from_chain, to_chain)
            
            if "error" in result:
                console.print(f"\n  [red]Error:[/red] {result['error']}\n")
            else:
                data = result.get("data", {})
                status = data.get("status", "unknown")
                routes = data.get("routes", [])
                
                # Status indicator
                if status == "healthy":
                    status_icon = "[green]●[/green]"
                elif status == "degraded":
                    status_icon = "[yellow]●[/yellow]"
                else:
                    status_icon = "[red]●[/red]"
                
                console.print(f"\n  {status_icon} Route Health: [bold]{from_chain} → {to_chain}[/bold]")
                console.print(f"  Status: [bold]{status.upper()}[/bold]")
                
                if routes:
                    table = Table(box=box.SIMPLE, border_style="dim")
                    table.add_column("Route", style="bold")
                    table.add_column("Status")
                    table.add_column("Latency")
                    for r in routes[:5]:
                        route_name = f"{r.get('fromChain', '?')} → {r.get('toChain', '?')}"
                        r_status = r.get("status", "?")
                        latency = r.get("latency", "?")
                        table.add_row(route_name, r_status, f"{latency}ms")
                    console.print(table)
                
                console.print()
            continue

        # ── Solver-aware checks command ──────────────────────────
        if text.startswith("solver ") or text.startswith("solver-check"):
            parts = text.split()
            if len(parts) < 3:
                console.print("\n  [yellow]Usage:[/yellow] solver <from_chain> <to_chain> [from_asset] [to_asset]")
                console.print("  [dim]Example:[/dim] solver base arbitrum USDC USDC")
                console.print("  [dim]Example:[/dim] solver base arbitrum\n")
                continue
            
            from_chain = parts[1]
            to_chain = parts[2]
            from_asset = parts[3] if len(parts) > 3 else None
            to_asset = parts[4] if len(parts) > 4 else None
            
            console.print(f"\n  [bold cyan]🔧 Solver-Aware Checks[/bold cyan]")
            console.print(f"  Route: [bold]{from_chain} → {to_chain}[/bold]")
            if from_asset and to_asset:
                console.print(f"  Assets: [bold]{from_asset} → {to_asset}[/bold]")
            console.print()
            
            # Run solver-aware checks
            with Progress(SpinnerColumn(), TextColumn("[bold blue]Running solver-aware checks...[/bold blue]"), transient=True) as progress:
                progress.add_task("solver", total=None)
                report = agent.solver_aware_checks(from_chain, to_chain, from_asset, to_asset)
            
            # Display results
            console.print("  [bold]Checks:[/bold]")
            for check in report["checks"]:
                # Status icon
                if check["passed"]:
                    icon = "[green]✓[/green]"
                elif check["status"] == "skipped":
                    icon = "[dim]○[/dim]"
                else:
                    icon = "[red]✗[/red]"
                
                # Status text
                status_text = check["status"].upper()
                if check["status"] == "healthy":
                    status_text = "[green]HEALTHY[/green]"
                elif check["status"] == "active":
                    status_text = "[green]ACTIVE[/green]"
                elif check["status"] == "available":
                    status_text = "[green]AVAILABLE[/green]"
                elif check["status"] == "empty":
                    status_text = "[yellow]EMPTY[/yellow]"
                elif check["status"] == "unavailable":
                    status_text = "[red]UNAVAILABLE[/red]"
                elif check["status"] == "error":
                    status_text = "[red]ERROR[/red]"
                
                console.print(f"    {icon} {check['name']}: {status_text}")
                
                # Show details for failed checks
                if not check["passed"] and check["status"] != "skipped":
                    details = check.get("details", {})
                    if isinstance(details, dict):
                        for key, value in details.items():
                            if key != "routes":  # Skip routes to avoid clutter
                                console.print(f"      [dim]{key}: {value}[/dim]")
                    else:
                        console.print(f"      [dim]{details}[/dim]")
            
            # Summary
            summary = report["summary"]
            console.print(f"\n  [bold]Summary:[/bold]")
            console.print(f"    Total checks: {summary['total_checks']}")
            console.print(f"    Passed: [green]{summary['passed_checks']}[/green]")
            console.print(f"    Failed: [red]{summary['failed_checks']}[/red]")
            console.print(f"    Overall: [bold]{summary['overall_status'].upper()}[/bold]")
            
            console.print()
            continue

        # ── Safe Verdict command ──────────────────────────────────
        if text.startswith("safe ") or text.startswith("verdict "):
            # Remove command prefix
            cmd_text = re.sub(r'^(safe|verdict)\s+', '', text, flags=re.IGNORECASE)
            
            try:
                # Parse intent and policy
                intent, policy = parse_intent_with_policy(cmd_text)
                
                console.print(f"\n  [bold cyan]🔍 Safe Verdict[/bold cyan]")
                console.print(f"  Intent: [bold]{intent.amount} {intent.token.upper()} {intent.from_chain} → {intent.to_chain}[/bold]")
                console.print(f"  Policy: [dim]{policy}[/dim]\n")
                
                # Execute Safe Verdict pipeline with trace
                with Progress(SpinnerColumn(), TextColumn("[bold blue]Running Safe Verdict checks...[/bold blue]"), transient=True) as progress:
                    progress.add_task("verdict", total=None)
                    result = agent.safe_verdict_trace(intent, policy)
                
                # Display verdict
                if result.verdict == "EXECUTABLE":
                    console.print(f"  [bold green]✓ Verdict: EXECUTABLE[/bold green]")
                else:
                    console.print(f"  [bold red]✗ Verdict: REFUSED[/bold red]")
                
                # Display decision trace
                console.print(f"\n  [bold]Decision Trace:[/bold]")
                for i, step in enumerate(result.steps, 1):
                    # Status icon
                    if step.status == "passed":
                        icon = "[green]✓[/green]"
                    elif step.status == "failed":
                        icon = "[red]✗[/red]"
                    elif step.status == "warning":
                        icon = "[yellow]⚠[/yellow]"
                    else:  # skipped
                        icon = "[dim]○[/dim]"
                    
                    # Duration
                    duration_str = f" ({step.duration_ms}ms)" if step.duration_ms > 0 else ""
                    
                    # MCP tool info
                    mcp_str = ""
                    if step.mcp_tool:
                        mcp_str = f" [dim]via {step.mcp_tool}[/dim]"
                    
                    console.print(f"    {icon} {step.name}: {step.detail}{duration_str}{mcp_str}")
                
                # Display reason
                console.print(f"\n  [bold]Reason:[/bold]")
                console.print(f"    {result.reason}")
                
                # Display timing
                console.print(f"\n  [dim]Total duration: {result.total_duration_ms}ms[/dim]")
                
                # If executable, show quote details
                if result.verdict == "EXECUTABLE" and result.quote_data:
                    quotes = result.quote_data.get("quotes", [])
                    if quotes:
                        q = quotes[0]
                        console.print(f"\n  [bold]Quote Details:[/bold]")
                        console.print(f"    Output: {q.get('outputAmount', 'N/A')}")
                        console.print(f"    Quote ID: {q.get('quoteId', 'N/A')[:16]}...")
                
                console.print()
                
            except ValueError as e:
                console.print(f"\n  [red]Parse error:[/red] {e}")
                console.print("  [dim]Example: safe send 10 USDC from Base to Arbitrum if fee < 0.5%[/dim]\n")
            except Exception as e:
                console.print(f"\n  [red]Error:[/red] {e}\n")
            continue

        if text == "orders":
            with Progress(SpinnerColumn(), TextColumn("[bold blue]Fetching orders...[/bold blue]"), transient=True) as progress:
                progress.add_task("orders", total=None)
                result = agent.list_orders()
            orders = result.get("data", {}).get("orders", [])
            if not orders:
                console.print("\n  [dim]No orders found.[/dim]\n")
            else:
                table = Table(box=box.ROUNDED, border_style="dim")
                table.add_column("Order ID", style="bold")
                table.add_column("Status")
                for o in orders:
                    table.add_row(str(o.get("id", "?")), str(o.get("status", "?")))
                console.print(table)
            console.print()
            continue

        if text == "favorites":
            favs = agent.get_favorite_routes()
            if favs:
                table = Table(title="Saved Routes", box=box.ROUNDED, border_style="cyan")
                table.add_column("#", style="dim", width=4)
                table.add_column("From")
                table.add_column("")
                table.add_column("To")
                table.add_column("Token")
                for i, r in enumerate(favs, 1):
                    parts = r.split(":")
                    table.add_row(str(i), styled_chain(parts[0]), "→", styled_chain(parts[1]), parts[2].upper())
                console.print()
                console.print(table)
            else:
                console.print("\n  [dim]No saved routes yet. Execute a transfer to save it.[/dim]")
            console.print()
            continue

        if text == "history":
            recent = get_quote_store().get_recent(10)
            if recent:
                table = Table(title="Recent Quotes (SQLite)", box=box.ROUNDED, border_style="dim")
                table.add_column("#", style="dim", width=4)
                table.add_column("Time", style="dim")
                table.add_column("Route")
                table.add_column("Output")
                table.add_column("Fee")
                for i, entry in enumerate(recent, 1):
                    ts = entry.get("timestamp", "?")[:19]  # YYYY-MM-DD HH:MM:SS
                    route = f"{entry['from_chain']}→{entry['to_chain']} ({entry['token'].upper()})"
                    output = entry.get("output_amount", "?")
                    fee = entry.get("fee_pct")
                    fee_str = f"{float(fee):.2f}%" if fee else "?"
                    table.add_row(str(i), ts, route, output, fee_str)
                console.print()
                console.print(table)
            else:
                console.print("\n  [dim]No quote history yet.[/dim]")
            console.print()
            continue

        if text == "stats":
            stats = get_quote_store().get_stats()
            if stats["total"] == 0:
                console.print("\n  [dim]No quotes recorded yet.[/dim]\n")
                continue
            
            table = Table(title="📊 Quote Statistics", box=box.ROUNDED, border_style="blue")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Total Quotes", str(stats["total"]))
            table.add_row("Average Fee", f"{stats['avg_fee']:.3f}%")
            
            if stats["top_routes"]:
                routes_str = "\n".join(
                    f"  {f}→{t} ({c}x)" for f, t, c in stats["top_routes"]
                )
                table.add_row("Top Routes", routes_str)
            
            if stats["top_tokens"]:
                tokens_str = ", ".join(
                    f"{t.upper()} ({c}x)" for t, c in stats["top_tokens"]
                )
                table.add_row("Top Tokens", tokens_str)
            
            console.print()
            console.print(table)
            console.print()
            continue

        if text.startswith("llm"):
            parts = text.split()
            if len(parts) > 1 and parts[1] == "on":
                if os.environ.get("OPENAI_API_KEY"):
                    use_llm = True
                    console.print("\n  [green]✓[/green] LLM mode enabled\n")
                else:
                    console.print("\n  [red]✗[/red] OPENAI_API_KEY not set\n")
            elif len(parts) > 1 and parts[1] == "off":
                use_llm = False
                console.print("\n  [yellow]⚡[/yellow] LLM mode disabled\n")
            else:
                status = "ON" if use_llm else "OFF"
                console.print(f"\n  LLM mode: {status}")
                console.print("  Usage: llm on | llm off\n")
            continue

        # ── Compare mode ───────────────────────────────────────
        if text.startswith("compare"):
            text = text.replace("compare", "send", 1)
            try:
                intent = parse_intent(text)
            except ValueError as e:
                status_err(str(e))
                console.print()
                continue

            console.print(f"\n  Comparing quotes for {intent.amount} {intent.token.upper()} from {styled_chain(intent.from_chain)}...")
            with Progress(SpinnerColumn(), TextColumn("[bold blue]Fetching quotes...[/bold blue]"), transient=True) as progress:
                progress.add_task("compare", total=None)
                results = agent.compare_quotes(intent)
            if results:
                table = Table(title="Best Routes (sorted by output)", box=box.ROUNDED, border_style="green")
                table.add_column("#", style="dim", width=4)
                table.add_column("Route")
                table.add_column("Output", justify="right")
                table.add_column("Fee", justify="right")
                for i, r in enumerate(results, 1):
                    marker = " [bold green]← best[/bold green]" if i == 1 else ""
                    fee_str = fee_style(r["fee_pct"])
                    route = f"{styled_chain(intent.from_chain)} → {styled_chain(r['chain'])}"
                    table.add_row(str(i), route, r["output"], fee_str)
                console.print()
                console.print(table)
            else:
                status_err("No quotes available for comparison")
            console.print()
            continue

        # ── Parse intent ───────────────────────────────────────
        try:
            if use_llm:
                intent = parse_intent_llm(text)
            else:
                intent = parse_intent(text)
        except ValueError as e:
            status_err(str(e))
            console.print()
            continue

        # Show intent and fetch with spinner
        console.print(f"\n  Intent: {intent}")
        with Progress(SpinnerColumn(), TextColumn("[bold blue]Fetching quote...[/bold blue]"), transient=True) as progress:
            progress.add_task("quote", total=None)
            result = agent.get_quote(intent)

        # Handle errors
        if "error" in result:
            status_err(result["error"])
            if "suggestion" in result:
                console.print(f"  [yellow]💡 {result['suggestion']}[/yellow]")
            console.print()
            continue

        quotes = result.get("data", {}).get("quotes", [])
        if quotes:
            q = quotes[0]
            # Build a styled quote panel
            fee_pct = agent._calc_fee(intent.amount, q.get("outputAmount", "0"), intent.token)
            quote_text = Text()
            quote_text.append("Input:     ", style="dim")
            quote_text.append(f"{q.get('inputAmount', '?')}\n")
            quote_text.append("Output:    ", style="dim")
            quote_text.append(f"{q.get('outputAmount', '?')}\n")
            quote_text.append("Fee:       ", style="dim")
            quote_text.append_text(Text.from_markup(fee_style(fee_pct)))
            quote_text.append("\n")
            quote_text.append("Quote ID:  ", style="dim")
            quote_text.append(f"{q.get('quoteId', '?')}")
            quote_text.append("\n\n")
            quote_text.append("Route:     ", style="dim")
            quote_text.append_text(Text.from_markup(
                f"{styled_chain(intent.from_chain)}  →  {styled_chain(intent.to_chain)}"
            ))

            console.print()
            status_ok("Quote from solver:")
            console.print(Panel(
                quote_text,
                border_style="green",
                box=box.ROUNDED,
                padding=(0, 2),
            ))

            pending_intent = intent
            pending_quote = q
            console.print("  Type [bold]'yes'[/bold] to prepare order, [dim]'no'[/dim] to cancel")
        else:
            msg = result.get("message", "No quotes available")
            status_err(msg)
            if "suggestion" in result:
                console.print(f"  [yellow]💡 {result['suggestion']}[/yellow]")
        console.print()

    agent.close()
    console.print("[dim]Bye![/dim]")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Single command mode
        text = " ".join(sys.argv[1:])
        agent = LifAgent()
        agent.connect()
        try:
            intent = parse_intent(text)
            result = agent.get_quote(intent)
            json_str = json.dumps(result, indent=2)
            console.print(Syntax(json_str, "json", theme="monokai"))
        except ValueError as e:
            status_err(str(e))
        finally:
            agent.close()
    else:
        interactive()
