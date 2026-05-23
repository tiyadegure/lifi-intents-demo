# 10 LI.FI Intents MCP Pitfalls I Hit While Building This Demo

A practical guide for developers building on LI.FI Intents MCP. These are real issues I encountered during development.

## 1. MCP response is SSE, not normal JSON

**Problem:** LI.FI Intents MCP uses Server-Sent Events (SSE) for responses, not standard JSON.

**Solution:** Parse SSE events properly. Look for `data:` lines and parse the JSON payload.

```python
# Wrong: Direct JSON parsing
result = response.json()

# Correct: Parse SSE events
for line in response.text.split('\n'):
    if line.startswith('data:'):
        data = json.loads(line[5:])
```

## 2. Need initialize + notifications/initialized

**Problem:** MCP protocol requires a handshake before any tool calls.

**Solution:** Always send `initialize` and `notifications/initialized` before calling tools.

```python
# Step 1: Initialize session
init_response = client.post(url, json={
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {...}
})
session_id = init_response.headers.get("mcp-session-id")

# Step 2: Send initialized notification
client.post(url, json={
    "jsonrpc": "2.0",
    "method": "notifications/initialized",
    "params": {}
}, headers={"mcp-session-id": session_id})
```

## 3. Session can expire

**Problem:** MCP sessions expire after a period of inactivity.

**Solution:** Implement session management with automatic re-initialization.

```python
def call(self, tool: str, args: dict):
    # Check if session is valid
    if not self.session_id or self._is_session_expired():
        self._init_session_sync()
    
    # Make the call
    result = self.mcp.call(tool, args)
    
    # Handle session expired errors
    if "No valid session ID" in str(result):
        self._init_session_sync()
        result = self.mcp.call(tool, args)
    
    return result
```

## 4. Token address differs per chain

**Problem:** USDC has different contract addresses on different chains.

**Solution:** Use chain-specific token addresses.

```python
TOKENS = {
    "usdc": {
        "8453": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # Base
        "42161": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",  # Arbitrum
        "1": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",    # Ethereum
    }
}

# Get address for specific chain
address = TOKENS["usdc"]["8453"]  # Base USDC
```

## 5. Human amount vs base units must be handled carefully

**Problem:** Users input "10 USDC" but MCP expects "10000000" (with 6 decimals).

**Solution:** Convert human-readable amounts to base units.

```python
TOKEN_DECIMALS = {
    "usdc": 6,
    "usdt": 6,
    "eth": 18,
}

def amount_to_raw(human_amount: str, token: str) -> str:
    decimals = TOKEN_DECIMALS.get(token.lower(), 18)
    amount_float = float(human_amount)
    raw_amount = int(amount_float * (10 ** decimals))
    return str(raw_amount)

# Example
raw = amount_to_raw("10", "usdc")  # Returns "10000000"
```

## 6. A route can exist but still have no quote

**Problem:** A route may be supported but have no available quotes due to liquidity.

**Solution:** Handle empty quotes gracefully.

```python
result = self.mcp.call("request-quote", args)
quotes = result.get("data", {}).get("quotes", [])

if not quotes:
    return {
        "error": "No quotes available for this route",
        "suggestion": "Try a different amount or chain"
    }
```

## 7. Solver liquidity can affect availability

**Problem:** Solver inventory may be empty, affecting quote availability.

**Solution:** Check solver inventory before relying on quotes.

```python
def check_solver_availability(self, from_chain, to_chain, from_asset, to_asset):
    inventory = self.mcp.call("get-quote-inventory", {
        "fromChain": from_chain,
        "toChain": to_chain,
        "fromAsset": from_asset,
        "toAsset": to_asset
    })
    
    quotes = inventory.get("data", {}).get("quotes", [])
    return len(quotes) > 0
```

## 8. Rate limiting requires retry/backoff

**Problem:** MCP server may rate-limit requests.

**Solution:** Implement exponential backoff retry.

```python
def call_with_retry(self, tool: str, args: dict, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            result = self.mcp.call(tool, args)
            return result
        except Exception as e:
            if "rate limit" in str(e).lower():
                delay = 2 ** attempt  # Exponential backoff
                time.sleep(delay)
                continue
            raise
    raise Exception("Max retries exceeded")
```

## 9. LLM output should not directly prepare orders

**Problem:** LLMs may hallucinate or produce invalid order parameters.

**Solution:** Always validate LLM output before executing.

```python
def validate_intent(intent: dict) -> bool:
    required_fields = ["from_chain", "to_chain", "token", "amount"]
    for field in required_fields:
        if field not in intent:
            return False
    
    # Validate chain names
    if intent["from_chain"] not in CHAINS:
        return False
    if intent["to_chain"] not in CHAINS:
        return False
    
    # Validate amount
    try:
        float(intent["amount"])
    except ValueError:
        return False
    
    return True
```

## 10. Developer UX needs visible traces

**Problem:** Developers need to see what's happening under the hood.

**Solution:** Implement decision traces with detailed logging.

```python
@dataclass
class DecisionStep:
    name: str
    status: str  # "passed", "failed", "skipped"
    detail: str
    duration_ms: int
    mcp_tool: str
    mcp_args: dict
    mcp_result: dict

@dataclass
class DecisionResult:
    verdict: str  # "EXECUTABLE" or "REFUSED"
    reason: str
    steps: List[DecisionStep]
    total_duration_ms: int
```

## Bonus: Common Error Messages

- **"No valid session ID"**: Session expired, re-initialize
- **"Unknown token"**: Token address not available on that chain
- **"No quotes returned"**: No liquidity for this route
- **"Rate limit exceeded"**: Implement retry with backoff

## Conclusion

Building on LI.FI Intents MCP requires careful handling of:
- Session management
- Token address resolution
- Amount unit conversion
- Error handling and retries
- Developer UX with visible traces

These pitfalls are common but solvable. The key is to implement robust error handling and provide clear feedback to developers.

## 11. Local vs Hosted MCP Server

**Problem:** The hosted LI.FI Intents MCP server uses session management, which can cause "No valid session ID" errors and other session-related issues.

**Solution:** Run the MCP server locally in stateless HTTP mode.

| | Local | Hosted |
|---|---|---|
| Mode | Stateless HTTP (no session ID) | Session-based |
| API params | Friendly: `fromChain` (slug), `fromToken` (symbol), `amount` (human-readable) | Raw chain IDs, contract addresses, base units |
| Reliability | High — no session expiry | Can return 403, session timeouts |
| Setup | `PORT=3333 node dist/transport-http.js` | No setup needed |

**Key differences:**
- Local runs in **stateless mode** — no session ID needed, the client handles this automatically
- Local uses **friendly params**: chain slugs (`Base`), token symbols (`USDC`), human-readable amounts (`10`)
- Hosted testnet may return **403 errors** without explanation
- The **solver network can be temporarily offline**, causing all quotes to return empty — this is not a bug, just wait and retry later
- **Session re-init** is not needed with the local server; the client skips it automatically

**Setup:**
```bash
git clone https://github.com/lifinance/lifi-intents-mcp
cd lifi-intents-mcp && npm install && npm run build
PORT=3333 node dist/transport-http.js
```

---

*Last updated: May 2026*
*Built for LI.FI Intents Mini Builder Challenge*
