# LI.FI Intents × AI Agent

> AI agents executing cross-chain token transfers through MCP protocol.
> No browser, no UI, just natural language → intent → solver → delivery.

## What is this?

A working AI agent that interacts with [LI.FI Intents](https://docs.li.fi/lifi-intents/introduction) through the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/). The agent discovers routes, requests quotes from the solver network, compares options, and executes cross-chain transfers — all through natural language.

## Quick Start

```bash
# Clone
git clone https://github.com/tiyadegure/lifi-intents-demo.git
cd lifi-intents-demo

# Install
python3 -m venv .venv
.venv/bin/pip install httpx

# Run CLI
.venv/bin/python3 -m lifi_agent

# Run Web UI
.venv/bin/pip install fastapi uvicorn
.venv/bin/python3 -m uvicorn lifi_agent.server:app --host 0.0.0.0 --port 8888
# Open http://localhost:8888
```

## Usage

```
You > send 10 USDC from Base to Arbitrum

  Intent: Intent(10 USDC base→arbitrum)
  Fetching quote...

  ✓ Quote from solver:
    Input:    10 USDC
    Output:   9.983725 USDC
    Quote ID: quote_xxx

  Type 'yes' to prepare order, 'no' to cancel

You > yes
  ✓ Order prepared!
    Route saved to favorites!
```

### Commands

- `send 10 USDC from Base to Arbitrum` — Execute a transfer
- `compare 10 USDC from Ethereum` — Compare quotes across chains
- `routes` — Show supported routes
- `orders` — Show recent orders
- `favorites` — Show saved routes
- `yes / no` — Confirm or cancel pending order

## Architecture

```
User Intent (natural language)
    ↓
Intent Parser (chain/token/amount extraction)
    ↓
MCP Client (session management, caching, retry)
    ↓
LI.FI Intents MCP Server (intents-mcp.li.fi/mcp)
    ↓
Order Server → Solver Network → Delivery
```

## Key Concepts

### LI.FI Intents
An intent-based cross-chain marketplace where:
- Users express **what** they want (e.g., "send 10 USDC from Base to Arbitrum")
- **Solvers** compete to fill orders using pre-published standing quotes
- Delivery is instant — solvers use their own capital, settlement happens later

### MCP (Model Context Protocol)
A standard protocol for AI tools. LI.FI provides a hosted MCP server at `intents-mcp.li.fi/mcp` with 13 tools for:
- Route discovery
- Quote requests
- Order management
- Solver operations

## MCP Server

**Endpoint:** `https://intents-mcp.li.fi/mcp`

**Integrator tools (no API key):**
- `get-supported-routes` — Discover chains & tokens
- `request-quote` — Get solver pricing
- `prepare-order` — Build on-chain order
- `submit-order` — Submit signed order
- `track-order` — Monitor settlement
- `list-orders` — List order history

**Solver tools (API key required):**
- `get-solver-identities` — View registered addresses
- `get-quote-inventory` — View standing quotes
- `submit-standing-quotes` — Submit/update pricing
- `debug-order` — Inspect order lifecycle
- `check-route-health` — Route diagnostics

## Project Structure

```
lifi-intents-demo/
├── lifi_agent/
│   ├── __init__.py       # Package exports
│   ├── __main__.py       # CLI entry point
│   ├── agent.py          # Agent, intent parser, interactive CLI
│   ├── mcp_client.py     # MCP client with caching & retry
│   └── server.py         # Web UI (FastAPI + reasoning traces)
├── demo/
│   └── agent_demo.py     # Terminal demo script (simulated)
├── remotion/
│   └── src/Demo.tsx      # Video generation (Remotion)
├── output/
│   └── demo_v2.mp4       # Demo video with narration
├── pyproject.toml        # SDK packaging (pip install lifi-agent)
├── requirements.txt
└── x_thread.md           # X Thread draft
```

## Demo Video

A polished video version with narration is available in `output/demo_v2.mp4` (70s, 1080p).

## Links

- **Docs:** https://docs.li.fi/lifi-intents/introduction
- **MCP Server:** https://intents-mcp.li.fi/mcp
- **Challenge:** https://lifi.notion.site/LI-FI-Intents-Mini-Builder-Challenge-366f0ff14ac78168a0cdd9f44a3c1f13

## Built with

- [LI.FI Intents MCP Server](https://intents-mcp.li.fi/mcp)
- [Remotion](https://www.remotion.dev/) — Video generation
- [edge-tts](https://github.com/rany2/edge-tts) — Narration
- [Hermes Agent](https://hermes-agent.nousresearch.com/) — AI agent platform
