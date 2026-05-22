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
from pathlib import Path
from .mcp_client import MCPClient

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
    """Run interactive CLI mode with multi-turn conversation."""
    import readline  # noqa: F401 — enables arrow key history

    agent = LifAgent()

    print("\n" + "=" * 60)
    print("  LI.FI Intents × AI Agent")
    print("  Cross-chain operations via natural language")
    print("=" * 60)
    print()

    try:
        info = agent.connect()
        print(f"✓ {info}")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        print("  Running in offline mode (cached data only)")
    print()

    print("Commands:")
    print("  send 10 USDC from Base to Arbitrum  — Execute a transfer")
    print("  compare 10 USDC from Ethereum       — Compare quotes across chains")
    print("  routes                               — Show supported routes")
    print("  orders                               — Show recent orders")
    print("  favorites                            — Show saved routes")
    print("  yes / confirm                        — Confirm pending order")
    print("  history                              — Show recent quotes")
    print("  quit                                 — Exit")
    print()

    pending_intent = None
    pending_quote = None

    while True:
        try:
            prompt = "Confirm > " if pending_intent else "You > "
            text = input(prompt).strip()
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
                    print(f"\n  Preparing order...")
                    result = agent.prepare_order(quote_id)
                    if "error" in result:
                        print(f"  ✗ {result['error']}")
                    else:
                        order = result.get("data", {})
                        print(f"  ✓ Order prepared!")
                        print(f"    Order ID: {order.get('id', '?')}")
                        print(f"    Status: {order.get('status', '?')}")
                        agent.pending_order = order
                        # Remember this route
                        agent.remember_route(pending_intent.from_chain, pending_intent.to_chain, pending_intent.token)
                        print(f"    Route saved to favorites!")
                else:
                    print("  ✗ No quote ID available")
            else:
                print("  ✗ No pending quote")
            pending_intent = None
            pending_quote = None
            print()
            continue

        if pending_intent and text in ("no", "n", "cancel"):
            print("\n  Cancelled.\n")
            pending_intent = None
            pending_quote = None
            continue

        # Cancel pending if new command
        if pending_intent:
            pending_intent = None
            pending_quote = None

        # ── Handle commands ────────────────────────────────────
        if text == "routes":
            result = agent.get_routes()
            count = result.get("data", {}).get("count", "?")
            routes_list = result.get("data", {}).get("routes", [])
            msg = result.get("message", "")
            print(f"\n  ✓ {count} routes available")
            if routes_list:
                # Show unique chain pairs
                pairs = set()
                for r in routes_list:
                    f = r.get("fromChain", "?")
                    t = r.get("toChain", "?")
                    pairs.add((f, t))
                for f, t in sorted(pairs)[:15]:
                    print(f"    {f} → {t}")
                if len(pairs) > 15:
                    print(f"    ... and {len(pairs)-15} more")
            if msg:
                print(f"  {msg}")
            print()
            continue

        if text == "orders":
            result = agent.list_orders()
            orders = result.get("data", {}).get("orders", [])
            if not orders:
                print("\n  No orders found.\n")
            else:
                for o in orders:
                    print(f"  {o.get('id', '?')} — {o.get('status', '?')}")
            print()
            continue

        if text == "favorites":
            favs = agent.get_favorite_routes()
            if favs:
                print(f"\n  Saved routes:")
                for i, r in enumerate(favs, 1):
                    parts = r.split(":")
                    print(f"    {i}. {parts[0].title()} → {parts[1].title()} ({parts[2].upper()})")
            else:
                print("\n  No saved routes yet. Execute a transfer to save it.")
            print()
            continue

        if text == "history":
            recent = agent.quote_history[-5:]
            if recent:
                print(f"\n  Recent quotes (last {len(recent)}):")
                for i, entry in enumerate(recent, 1):
                    ts = time.strftime("%H:%M:%S", time.localtime(entry["timestamp"]))
                    quotes = entry["result"].get("data", {}).get("quotes", [])
                    output = quotes[0].get("outputAmount", "?") if quotes else "?"
                    print(f"    {i}. [{ts}] {entry['intent']} → {output}")
            else:
                print("\n  No quote history yet.")
            print()
            continue

        # ── Compare mode ───────────────────────────────────────
        if text.startswith("compare"):
            text = text.replace("compare", "send", 1)
            try:
                intent = parse_intent(text)
            except ValueError as e:
                print(f"\n  ✗ {e}\n")
                continue

            print(f"\n  Comparing quotes for {intent.amount} {intent.token.upper()} from {intent.from_chain.title()}...")
            results = agent.compare_quotes(intent)
            if results:
                print(f"\n  ✓ Best routes (sorted by fee):\n")
                for i, r in enumerate(results, 1):
                    marker = " ← best" if i == 1 else ""
                    print(f"    {i}. {intent.from_chain.title()} → {r['chain'].title()}")
                    print(f"       Output: {r['output']} | Fee: ~{r['fee_pct']}%{marker}")
                print()
            else:
                print("  ✗ No quotes available for comparison\n")
            continue

        # ── Parse intent ───────────────────────────────────────
        try:
            intent = parse_intent(text)
        except ValueError as e:
            print(f"\n  ✗ {e}\n")
            continue

        print(f"\n  Intent: {intent}")
        print(f"  Fetching quote...")

        result = agent.get_quote(intent)

        # Handle errors with suggestions
        if "error" in result:
            print(f"  ✗ {result['error']}")
            if "suggestion" in result:
                print(f"  💡 {result['suggestion']}")
            print()
            continue

        quotes = result.get("data", {}).get("quotes", [])
        if quotes:
            q = quotes[0]
            print(f"\n  ✓ Quote from solver:")
            print(f"    Input:    {q.get('inputAmount', '?')}")
            print(f"    Output:   {q.get('outputAmount', '?')}")
            print(f"    Quote ID: {q.get('quoteId', '?')}")

            # Store for confirmation
            pending_intent = intent
            pending_quote = q
            print(f"\n  Type 'yes' to prepare order, 'no' to cancel")
        else:
            msg = result.get("message", "No quotes available")
            print(f"  ✗ {msg}")
            if "suggestion" in result:
                print(f"  💡 {result['suggestion']}")
        print()

    agent.close()
    print("Bye!")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Single command mode
        text = " ".join(sys.argv[1:])
        agent = LifAgent()
        agent.connect()
        try:
            intent = parse_intent(text)
            result = agent.get_quote(intent)
            print(json.dumps(result, indent=2))
        except ValueError as e:
            print(f"Error: {e}")
        finally:
            agent.close()
    else:
        interactive()
