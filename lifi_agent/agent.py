"""
LI.FI Intents Agent — AI-powered cross-chain assistant.

Usage:
    python3 -m lifi_agent                    # Interactive mode
    python3 -m lifi_agent "send 10 USDC from Base to Arbitrum"  # Single command
"""

import sys
import json
import os
import time
import sqlite3
from contextlib import contextmanager
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
              fee_pct: str, quote_id: str):
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

quote_store = QuoteStore()

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

# Dummy address for demo (replace with real wallet in production)
DEMO_ADDRESS = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


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
    import re
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
            "amount": intent.amount,
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
                quote_store.store(
                    intent_repr=repr(intent),
                    from_chain=intent.from_chain,
                    to_chain=intent.to_chain,
                    token=intent.token,
                    input_amount=intent.amount,
                    output_amount=output,
                    fee_pct=self._calc_fee(intent.amount, output),
                    quote_id=q.get("quoteId", "")
                )

        return result

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
                        "fee_pct": self._calc_fee(intent.amount, output),
                    })
            except Exception:
                continue

        # Sort by output amount (higher is better)
        def parse_output(r):
            try:
                return float(''.join(c for c in r.get("output", "0") if c.isdigit() or c == '.'))
            except ValueError:
                return 0

        results.sort(key=parse_output, reverse=True)
        return results

    def _calc_fee(self, input_amount: str, output_amount: str) -> str:
        """Calculate fee percentage."""
        try:
            inp = float(input_amount)
            # Strip non-numeric chars (e.g. " USDC")
            out_str = ''.join(c for c in output_amount if c.isdigit() or c == '.')
            out = float(out_str)
            if inp == 0:
                return "999"
            fee = (inp - out) / inp * 100
            return f"{fee:.2f}"
        except (ValueError, ZeroDivisionError):
            return "999"

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

    def close(self):
        self.mcp.close()


# ── Interactive CLI ─────────────────────────────────────────────────
def interactive():
    """Run interactive CLI mode with Rich TUI and auto-completion."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.styles import Style as PTStyle

    agent = LifAgent()

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
    help_table.add_row("[cyan]compare[/cyan] 10 USDC from Ethereum", "Compare quotes across chains")
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
    commands = ["send", "compare", "routes", "orders", "favorites", "wallet",
                "history", "stats", "quit"]
    all_completions = commands + chain_names + token_names + [
        "from", "to", "bridge", "transfer",
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
            recent = quote_store.get_recent(10)
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
                    fee = entry.get("fee_pct", "?")
                    fee_str = f"{float(fee):.2f}%" if fee and fee != "999" else "?"
                    table.add_row(str(i), ts, route, output, fee_str)
                console.print()
                console.print(table)
            else:
                console.print("\n  [dim]No quote history yet.[/dim]")
            console.print()
            continue

        if text == "stats":
            stats = quote_store.get_stats()
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
            fee_pct = agent._calc_fee(intent.amount, q.get("outputAmount", "0"))
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
