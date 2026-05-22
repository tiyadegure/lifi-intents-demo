# How to Build a Cross-Chain AI Agent with LI.FI Intents + MCP

*By Tiya Degurechaff · LI.FI Intents Builder Challenge*

---

## Introduction

What if you could send USDC from Base to Arbitrum just by typing *"send 10 USDC base->arb"* in natural language?

In this tutorial, I'll show you how I built an AI Agent that understands cross-chain intents and executes them through the LI.FI Intents MCP Server. The result is a fully functional tool with a Web UI, CLI interface, and developer SDK.

![Web UI Screenshot](./assets/web-ui-screenshot.png)

---

## What We're Building

A **Cross-Chain AI Agent** that:
- Parses natural language intents ("send 10 USDC from Base to Arbitrum")
- Connects to the LI.FI Intents MCP Server for real-time quotes
- Provides a Web UI with quote comparison, solver analytics, and transaction tracking
- Includes a Rich CLI with auto-completion and color-coded output
- Packages as an installable SDK (`pip install lifi-agent`)

---

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  User Input │ ──▶ │  AI Agent   │ ──▶ │ MCP Client  │ ──▶ │ LI.FI MCP   │
│  (NL text)  │     │  (Parser)   │     │  (Retry +   │     │  Server     │
└─────────────┘     └─────────────┘     │   Cache)    │     └─────────────┘
                                        └─────────────┘
                                              │
                                              ▼
                                        ┌─────────────┐
                                        │ Cross-chain  │
                                        │   Quote      │
                                        └─────────────┘
```

**Key Components:**
1. **Intent Parser** — Converts natural language to structured intents
2. **MCP Client** — Handles session management, caching, and retry logic
3. **AI Agent** — Orchestrates the flow and manages conversation state
4. **Web UI** — Real-time dashboard with quote comparison and solver analytics
5. **CLI** — Interactive terminal with rich formatting and auto-completion

---

## Part 1: Setting Up the MCP Client

The LI.FI Intents MCP Server uses the Model Context Protocol. Here's how to connect:

```python
import httpx
import json

class MCPClient:
    def __init__(self, url="https://intents-mcp.li.fi/mcp"):
        self.url = url
        self.session_id = None
        self._cache = {}
    
    def connect(self):
        """Initialize MCP session."""
        r = httpx.post(self.url, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "my-agent", "version": "1.0"}
            }
        })
        self.session_id = r.headers.get("mcp-session-id")
        return r.json()
```

### Handling Rate Limits

The MCP server has rate limits. Implement exponential backoff:

```python
def call(self, tool: str, args: dict, retries: int = 3):
    """Call an MCP tool with retry logic."""
    for attempt in range(retries):
        try:
            # Fresh session per call
            session = self._new_session()
            result = self._call_tool(session, tool, args)
            
            if "error" not in result:
                return result
                
            if "No valid session" in str(result.get("error")):
                wait = 2 ** attempt  # 2s, 4s, 8s
                logger.warning(f"Retry {attempt+1}/{retries}, waiting {wait}s...")
                time.sleep(wait)
                continue
                
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2)
    
    return {"error": "Max retries exceeded"}
```

### Caching for Performance

Cache responses to avoid repeated calls:

```python
CACHE_TTL = 300  # 5 minutes

def call(self, tool, args, use_cache=True):
    cache_key = f"{tool}:{json.dumps(args, sort_keys=True)}"
    
    if use_cache and cache_key in self._cache:
        ts, data = self._cache[cache_key]
        if time.time() - ts < self.CACHE_TTL:
            return data  # Return cached result
    
    result = self._call_mcp(tool, args)
    self._cache[cache_key] = (time.time(), result)
    return result
```

---

## Part 2: Building the Intent Parser

The parser converts natural language to structured intents:

```python
import re

CHAINS = {
    "ethereum": "1", "base": "8453", "arbitrum": "42161",
    "optimism": "10", "polygon": "137", "bsc": "56"
}

# Support aliases
CHAIN_ALIASES = {
    "arb": "arbitrum", "poly": "polygon", "op": "optimism",
    "avax": "avalanche", "eth": "ethereum"
}

def parse_intent(text: str) -> Intent:
    """Parse 'send 10 USDC base->arb' into an Intent."""
    text = text.lower().strip()
    
    # Extract amount and token
    match = re.search(r'(\d+\.?\d*)\s*(usdc|usdt|eth)', text)
    if not match:
        raise ValueError("Couldn't find amount and token")
    
    amount = match.group(1)
    token = match.group(2)
    
    # Extract chains (support arrow syntax: base->arb, eth→poly)
    arrow_match = re.search(r'(\w+)[->→]+(\w+)', text)
    if arrow_match:
        from_chain = resolve_chain(arrow_match.group(1))
        to_chain = resolve_chain(arrow_match.group(2))
    else:
        # Fall back to "from X to Y" pattern
        from_match = re.search(r'from\s+(\w+)', text)
        to_match = re.search(r'to\s+(\w+)', text)
        from_chain = resolve_chain(from_match.group(1))
        to_chain = resolve_chain(to_match.group(1))
    
    return Intent(from_chain, to_chain, token, amount)

def resolve_chain(name: str) -> str:
    """Resolve chain name or alias."""
    name = name.lower()
    return CHAIN_ALIASES.get(name, name)
```

**Supported formats:**
- `send 10 USDC from Base to Arbitrum`
- `bridge 50 USDC eth to poly`
- `transfer 100 USDC base->arb`
- `10 USDC base→arbitrum`

---

## Part 3: Building the AI Agent

The agent orchestrates the flow:

```python
class CrossChainAgent:
    def __init__(self):
        self.mcp = MCPClient()
        self.history = []
    
    def get_quote(self, intent: Intent) -> dict:
        """Get a cross-chain quote."""
        # Validate route exists
        routes = self.mcp.call("get-supported-routes")
        if not self._route_exists(routes, intent):
            return {"error": f"No route for {intent.from_chain}→{intent.to_chain}"}
        
        # Get quote from MCP
        result = self.mcp.call("request-quote", {
            "fromChain": intent.from_chain_id(),
            "toChain": intent.to_chain_id(),
            "fromToken": intent.from_token_address(),
            "toToken": intent.to_token_address(),
            "amount": intent.amount,
            "userAddress": intent.address,
        })
        
        # Track in history
        self.history.append({
            "intent": repr(intent),
            "result": result,
            "timestamp": time.time()
        })
        
        return result
    
    def compare_quotes(self, intent: Intent, chains: list = None):
        """Compare quotes across multiple chains."""
        chains = chains or ["arbitrum", "optimism", "base", "polygon"]
        results = []
        
        for chain in chains:
            if chain == intent.from_chain:
                continue
            alt = Intent(intent.from_chain, chain, intent.token, intent.amount)
            quote = self.get_quote(alt)
            if "data" in quote:
                results.append({
                    "chain": chain,
                    "output": quote["data"]["quotes"][0]["outputAmount"],
                    "fee": self._calc_fee(intent.amount, quote)
                })
        
        # Sort by output (higher is better)
        return sorted(results, key=lambda x: float(x["output"]), reverse=True)
```

---

## Part 4: Building the Web UI

The Web UI is a single FastAPI endpoint with embedded HTML/CSS/JS:

```python
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()
agent = CrossChainAgent()

@app.get("/api/quote")
async def get_quote(from_chain: str, to_chain: str, 
                    token: str, amount: str):
    intent = Intent(from_chain, to_chain, token, amount)
    return agent.get_quote(intent)

@app.get("/api/compare")
async def compare(from_chain: str, token: str, amount: str):
    intent = Intent(from_chain, "arbitrum", token, amount)
    return agent.compare_quotes(intent)
```

**Key UI Features:**
- **Quote Result** — Shows input/output amounts with fee percentage
- **Route Comparison** — Compares quotes across chains, highlights best option
- **Agent Reasoning** — Displays each MCP call with timing (deduplicates failures)
- **Solver Network** — Shows active solvers and their chain coverage
- **Transaction Tracker** — Visual timeline of order status

### Visual Design

- Dark navy theme (`#060a13` background)
- Purple accent (`#6c5ce7`)
- Inter font for readability
- CSS animations for smooth transitions
- Mobile responsive (1 column on small screens)

---

## Part 5: Building the CLI

The CLI uses Rich for formatting and prompt_toolkit for auto-completion:

```python
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter

console = Console()
completer = WordCompleter([
    'send', 'compare', 'routes', 'orders', 'history',
    'base', 'arbitrum', 'optimism', 'polygon',
    'USDC', 'USDT', 'ETH'
])

session = PromptSession(completer=completer)

def interactive():
    console.print(Panel("LI.FI Intents × AI Agent", 
                       subtitle="Cross-chain via natural language"))
    
    while True:
        text = session.prompt("You > ")
        if text == "quit":
            break
        
        intent = parse_intent(text)
        with console.status("Fetching quote..."):
            result = agent.get_quote(intent)
        
        if "error" in result:
            console.print(f"[red]✗ {result['error']}[/red]")
        else:
            q = result["data"]["quotes"][0]
            table = Table(title="Quote Result")
            table.add_row("Input", f"{intent.amount} {intent.token.upper()}")
            table.add_row("Output", q["outputAmount"])
            table.add_row("Fee", f"{calc_fee(intent.amount, q):.2f}%")
            console.print(table)
```

---

## Part 6: Packaging as an SDK

Make it installable with `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "lifi-agent"
version = "0.1.0"
description = "AI Agent for LI.FI Intents cross-chain operations"
dependencies = ["httpx>=0.27"]

[project.scripts]
lifi-agent = "lifi_agent.agent:main"
```

Install with: `pip install lifi-agent`

---

## Key Learnings

### 1. MCP Session Management
The MCP server rate-limits by session. Create a fresh session for each call to avoid hitting limits.

### 2. Caching is Essential
MCP calls are slow (500ms-2s). Cache responses for 5 minutes to improve UX.

### 3. Graceful Degradation
When MCP fails, fall back to cached data with a warning message.

### 4. Arrow Syntax is Intuitive
Users prefer `base->arb` over `from Base to Arbitrum`. Support both.

### 5. Visual Feedback Matters
Show each step of the agent's reasoning process. Users trust what they can see.

---

## Try It Yourself

```bash
# Clone the repo
git clone https://github.com/tiyadegure/lifi-intents-demo
cd lifi-intents-demo

# Install dependencies
pip install -e .

# Run the CLI
python -m lifi_agent

# Or start the Web UI
uvicorn lifi_agent.server:app --port 8888
```

**Example commands:**
- `send 10 USDC base->arb`
- `compare 50 USDC from Ethereum`
- `routes`
- `history`

---

## What's Next

- **Multi-chain wallet integration** — Connect real wallets for actual transfers
- **Solver dashboard** — Real-time solver performance metrics
- **Slack/Telegram bot** — Cross-chain operations via messaging
- **Transaction monitoring** — WebSocket-based order tracking

---

## Resources

- [LI.FI Intents Documentation](https://docs.li.fi/lifi-intents/introduction)
- [LI.FI MCP Server](https://intents-mcp.li.fi/mcp)
- [Project GitHub](https://github.com/tiyadegure/lifi-intents-demo)
- [MCP Protocol Spec](https://modelcontextprotocol.io)

---

*Built for the LI.FI Intents Builder Challenge. Special thanks to the LI.FI team for the MCP server and documentation.*
