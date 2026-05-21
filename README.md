# LI.FI Intents × AI Agent Demo

> AI agents executing cross-chain token transfers through MCP protocol.
> No browser, no UI, just natural language → intent → solver → delivery.

## What is this?

A demo showing how AI agents can interact with [LI.FI Intents](https://docs.li.fi/lifi-intents/introduction) through the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/). The agent discovers routes, requests quotes from the solver network, and explains the intent-based architecture — all through MCP tool calls.

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

### Architecture
```
User Intent → MCP Server → Order Server → Solver Network
                                              ↓
User receives tokens ← Oracle Verification ← Delivery
```

## Demo Script

Run the terminal demo:
```bash
python3 demo/agent_demo.py
```

This shows a simulated AI agent conversation where the agent:
1. Connects to the LI.FI Intents MCP Server
2. Discovers 812+ routes across 15+ chains
3. Requests a cross-chain quote (10 USDC Base → Arbitrum)
4. Explains the intent-based architecture

## Remotion Video

A polished video version with narration is available in `output/demo_v2.mp4`.

To re-render:
```bash
cd remotion
npx remotion render LifiIntentsDemo --output=../output/demo_v2.mp4 --codec=h264
```

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
- `unregister-solver` — Remove solver address

## LI.FI Intents

- **Docs:** https://docs.li.fi/lifi-intents/introduction
- **MCP Server:** https://intents-mcp.li.fi/mcp
- **OIF:** Open Intents Framework (Ethereum Foundation)
- **Supported chains:** Base, Arbitrum, Ethereum, Optimism, Polygon, BSC, Solana, Tron, Soneium, and more
- **Active routes:** 812+ across 15+ chains

## Built with

- [LI.FI Intents MCP Server](https://intents-mcp.li.fi/mcp)
- [Remotion](https://www.remotion.dev/) — Video generation
- [edge-tts](https://github.com/rany2/edge-tts) — Narration
- [Hermes Agent](https://hermes-agent.nousresearch.com/) — AI agent platform
