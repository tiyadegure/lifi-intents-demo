"""
LI.FI Intents Agent — AI-powered cross-chain assistant.

Usage:
    python3 -m lifi_agent                    # Interactive mode
    python3 -m lifi_agent "send 10 USDC from Base to Arbitrum"  # Single command
"""

import sys
import json
from .mcp_client import MCPClient

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


def parse_intent(text: str) -> Intent:
    """Parse natural language into a cross-chain intent.

    Examples:
        "send 10 USDC from Base to Arbitrum"
        "bridge 50 USDT polygon to ethereum"
        "transfer 0.5 ETH from optimism to base"
    """
    import re
    text = text.lower().strip()

    # Extract amount + token
    amount_match = re.search(r'(\d+\.?\d*)\s*(usdc|usdt|eth|weth)', text)
    if not amount_match:
        raise ValueError("Couldn't find amount and token. Try: 'send 10 USDC from Base to Arbitrum'")
    amount = amount_match.group(1)
    token = amount_match.group(2).replace("weth", "eth")

    # Extract chains by position in text (earliest = from, latest = to)
    chain_positions = []
    for name in CHAINS:
        pos = text.find(name)
        if pos >= 0:
            chain_positions.append((pos, name))
    chain_positions.sort()

    if len(chain_positions) < 2:
        found = [c[1] for c in chain_positions]
        raise ValueError(f"Need two chains. Found: {found}. Supported: {', '.join(CHAINS.keys())}")

    # Use "from X to Y" pattern if available, else use text position
    from_match = re.search(r'from\s+(\w+)', text)
    to_match = re.search(r'to\s+(\w+)', text)

    if from_match and from_match.group(1) in CHAINS:
        from_chain = from_match.group(1)
    else:
        from_chain = chain_positions[0][1]

    if to_match and to_match.group(1) in CHAINS:
        to_chain = to_match.group(1)
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

    def connect(self):
        info = self.mcp.connect()
        server = info.get("serverInfo", {})
        return f"Connected to {server.get('name', '?')} v{server.get('version', '?')}"

    def get_routes(self) -> dict:
        """Get all supported routes."""
        return self.mcp.call("get-supported-routes", {})

    def get_quote(self, intent: Intent) -> dict:
        """Get a cross-chain quote with route validation."""
        # Check if route exists in supported routes
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

        # If quote fails with "Unknown token", suggest alternative
        raw = result.get("raw", "")
        if "Unknown token" in raw:
            result["suggestion"] = f"Token {intent.token.upper()} may not be available on {intent.from_chain}. Try: routes"
            result["error"] = raw

        return result

    def prepare_order(self, quote_id: str, address: str = DEMO_ADDRESS) -> dict:
        """Prepare an order from a quote."""
        return self.mcp.call("prepare-order", {"quoteId": quote_id, "userAddress": address})

    def track_order(self, order_id: str) -> dict:
        """Track an order's status."""
        return self.mcp.call("track-order", {"orderId": order_id})

    def list_orders(self, limit: int = 5) -> dict:
        """List recent orders."""
        return self.mcp.call("list-orders", {"limit": limit})

    def close(self):
        self.mcp.close()


# ── Interactive CLI ─────────────────────────────────────────────────
def interactive():
    """Run interactive CLI mode."""
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
    print("  send 10 USDC from Base to Arbitrum")
    print("  quote 50 USDT polygon to ethereum")
    print("  routes")
    print("  orders")
    print("  quit")
    print()

    while True:
        try:
            text = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not text:
            continue
        if text in ("quit", "exit", "q"):
            break

        # Handle commands
        if text == "routes":
            result = agent.get_routes()
            count = result.get("data", {}).get("count", "?")
            msg = result.get("message", "")
            print(f"\n  ✓ {count} routes available")
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

        # Parse intent
        try:
            intent = parse_intent(text)
        except ValueError as e:
            print(f"\n  ✗ {e}\n")
            continue

        print(f"\n  Intent: {intent}")
        print(f"  Fetching quote...")

        result = agent.get_quote(intent)

        if "error" in result:
            print(f"  ✗ Error: {result['error']}\n")
            continue

        quotes = result.get("data", {}).get("quotes", [])
        if quotes:
            q = quotes[0]
            print(f"\n  ✓ Quote from solver:")
            print(f"    Input:    {q.get('inputAmount', '?')}")
            print(f"    Output:   {q.get('outputAmount', '?')}")
            print(f"    Quote ID: {q.get('quoteId', '?')}")
            msg = result.get("message", "")
            if msg:
                print(f"    {msg}")
        else:
            print(f"  ✗ No quotes available")
            print(f"    {result.get('message', '')}")
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
