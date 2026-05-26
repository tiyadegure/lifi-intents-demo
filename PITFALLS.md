# 10 Pitfalls Building on LI.FI Intents MCP

A practical guide for developers — real issues I hit during development and how to solve them.

---

## 1. MCP Responses Are SSE, Not JSON

**What happens:** You call an MCP tool and expect a JSON response, but get a stream of `data:` lines instead.

**Fix:** Parse Server-Sent Events properly — extract the last valid `data:` payload.

```python
# ❌ Won't work
result = response.json()

# ✅ Parse SSE
last_result = None
for line in response.text.split('\n'):
    if line.strip().startswith('data:') and line.strip()[5:].strip():
        d = json.loads(line.strip()[5:])
        for c in d.get("result", {}).get("content", []):
            if c.get("type") == "text":
                last_result = json.loads(c["text"])
```

---

## 2. You Must Handshake Before Calling Tools

**What happens:** First tool call fails with "No valid session" or silent error.

**Fix:** MCP protocol requires a two-step handshake before any tool calls:

```python
# Step 1: Initialize
r = client.post(url, json={
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "my-agent", "version": "1.0"}
    }
})
session_id = r.headers.get("mcp-session-id")

# Step 2: Acknowledge
client.post(url, json={
    "jsonrpc": "2.0", "method": "notifications/initialized", "params": {}
}, headers={"mcp-session-id": session_id})

# Now you can call tools ✅
```

---

## 3. Token Addresses Are Chain-Specific

**What happens:** You use one USDC address for all chains. Quotes fail or return wrong tokens.

**Fix:** Each chain has its own contract address for the same token:

```python
TOKENS = {
    "usdc": {
        "1":    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # Ethereum
        "8453": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # Base
        "42161":"0xaf88d065e77c8cC2239327C5EDb3A432268e5831",  # Arbitrum
    }
}
```

---

## 4. Amount Units: Human-Readable vs Raw

**What happens:** User types "10 USDC" but MCP expects `"10000000"` (6 decimals).

**Fix:** Convert based on token decimals:

```python
TOKEN_DECIMALS = {"usdc": 6, "usdt": 6, "eth": 18, "weth": 18}

def amount_to_raw(human: str, token: str) -> str:
    decimals = TOKEN_DECIMALS.get(token.lower(), 18)
    return str(int(float(human) * 10 ** decimals))

amount_to_raw("10", "usdc")  # → "10000000"
```

> **Note:** The local MCP server accepts human-readable amounts and handles conversion internally. The hosted API may require raw units — check which mode you're targeting.

---

## 5. A Supported Route ≠ An Available Quote

**What happens:** `get-supported-routes` returns a route, but `request-quote` returns empty quotes.

**Fix:** Route support and quote availability are separate concepts. Always handle empty quotes:

```python
result = mcp.call("request-quote", args)
quotes = result.get("data", {}).get("quotes", [])

if not quotes:
    return {"error": "No quotes available", "hint": "Try different amount or chain pair"}
```

Common causes:
- Solver temporarily offline
- Amount too small or too large for the route
- Low liquidity on the token pair

---

## 6. Solver Inventory Affects Everything

**What happens:** A route looks healthy but quotes are consistently empty.

**Fix:** Check solver inventory to understand coverage:

```python
inventory = mcp.call("get-quote-inventory", {
    "fromChain": "8453", "toChain": "42161",
    "fromAsset": "0x8335...", "toAsset": "0xaf88..."
})
quotes = inventory.get("data", {}).get("quotes", [])
# len(quotes) tells you how many solvers are actively quoting this route
```

---

## 7. Rate Limiting Needs Backoff

**What happens:** Rapid tool calls get throttled or fail.

**Fix:** Implement exponential backoff with a minimum call interval:

```python
MIN_CALL_INTERVAL = 1.0  # seconds between calls

def call_with_retry(mcp, tool, args, retries=2):
    for attempt in range(retries + 1):
        try:
            return mcp.call(tool, args)
        except Exception as e:
            if attempt < retries:
                time.sleep(2 ** (attempt + 1))  # 2s, 4s
            else:
                raise
```

---

## 8. Never Trust LLM Output for Orders

**What happens:** LLM-generated parameters have hallucinated chain names, invalid addresses, or wrong amounts.

**Fix:** Always validate before executing:

```python
def validate_intent(intent: dict) -> bool:
    if intent["from_chain"] not in KNOWN_CHAINS:
        return False
    if intent["to_chain"] not in KNOWN_CHAINS:
        return False
    try:
        float(intent["amount"])
    except ValueError:
        return False
    return True
```

This project uses a **deterministic regex parser** by default — zero LLM dependency, consistent output. LLM parsing is available as an optional fallback.

---

## 9. Decision Traces Are Not Optional

**What happens:** Your agent makes a decision but you can't explain why.

**Fix:** Log every step with tool name, input, output, and timing:

```python
@dataclass
class DecisionStep:
    name: str           # "Check Route Health"
    status: str         # "passed", "failed", "skipped"
    detail: str         # "Status: HEALTHY"
    duration_ms: int    # 42
    mcp_tool: str       # "check-route-health"
    mcp_args: dict      # raw input to MCP
    mcp_result: dict    # raw output from MCP
```

This is the core of the **Safe Verdict** approach — every decision is auditable.

---

## 10. Common Error Messages

| Error | Cause | Fix |
|-------|-------|-----|
| `"No valid session ID"` | Session expired | Re-initialize the MCP session |
| `"Unknown token"` | Token not available on that chain | Check token address mapping |
| `"No quotes returned"` | No solver coverage | Try different amount/chain, or retry later |
| `"No data in response"` | SSE parsing failed | Check response format, handle empty data lines |

---

## Bonus: Three-Mode Architecture

For development, use a three-mode fallback pattern:

| Mode | Env Var | Behavior |
|------|---------|----------|
| **Local MCP** | *(default)* | Real solver data via local MCP server |
| **Mock Fallback** | auto | Falls back to mock if server unreachable |
| **Mock Forced** | `LIFI_AGENT_MOCK_MODE=1` | Always use mock data |
| **Strict** | `LIFI_AGENT_STRICT_MODE=1` | Require real MCP, crash if unavailable |

This lets you develop and test the full pipeline without needing a running MCP server, while still using real data in production.

---

*Built for [LI.FI Intents Mini Builder Challenge](https://lifi.notion.site/LI-FI-Intents-Mini-Builder-Challenge-366f0ff14ac78168a0cdd9f44a3c1f13)*
