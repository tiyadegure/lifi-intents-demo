# LI.FI Intents Developer Playground

A solver-aware technical demo for [LI.FI Intents MCP](https://docs.li.fi/lifi-intents/introduction).

It turns natural language like:

> "send 10 USDC from Base to Arbitrum only if fee < 0.5%"

into:

1. **Structured intent** — amount, token, chains
2. **Policy constraints** — max fee, min output, route health
3. **LI.FI MCP quote request** — real-time solver quotes
4. **Route health / solver checks** — availability, latency
5. **Visible decision trace** — every step logged with timing
6. **EXECUTABLE or REFUSED verdict** — policy-driven decision

**Live demo → [lifi.degure.me](http://lifi.degure.me)**

---

## How it works

```
Natural language input
  → Intent parser (regex or LLM)
    → Policy extractor ("only if fee < 0.5%")
      → MCP tool call (get-supported-routes, request-quote)
        → Solver-aware checks (route health, quote availability)
          → Safe Verdict (EXECUTABLE / REFUSED)
```

The parser uses a **deterministic regex engine** by default, with optional LLM fallback (OpenAI-compatible API). This means it works offline, with zero API keys, and produces consistent structured output every time.

---

## Features

- **Safe Verdict** — policy-driven decision engine with EXECUTABLE / REFUSED output
- **Decision Trace** — step-by-step audit log with MCP tool names and timing
- **Solver-Aware Checks** — route health, quote availability, solver inventory
- **Doctor** — `python -m lifi_agent doctor` to diagnose MCP connectivity
- **CLI** — interactive terminal with tab completion, rich formatting
- **Web UI** — three-column layout: Intent → Structured Output → Decision Trace
- **PITFALLS.md** — 10 real pitfalls encountered building against LI.FI Intents MCP

---

## Local MCP Server Setup

The LI.FI Intents MCP server can run locally in stateless HTTP mode, which is more reliable than the hosted version (which has session management issues).

### Three modes

The CLI supports three modes and automatically selects the best one on startup:

- **Primary: Local MCP Mode** — connects to the local MCP server at `localhost:3333/mcp` (configurable via `LIFI_MCP_URL`). Full solver quotes, real-time route health, and inventory checks.
- **Fallback: Mock Mode** — if the local MCP server is not running, the CLI automatically falls back to mock data. Useful for testing the UI and Safe Verdict logic without an MCP server.
- **Strict Mode** — forces real MCP only. If the server is unreachable, the CLI raises an error instead of falling back to mock. Use this when you need to guarantee real solver data.

To force mock mode regardless of server availability:

```bash
export LIFI_AGENT_MOCK_MODE=1
```

To enable strict mode (no mock fallback):

```bash
export LIFI_AGENT_STRICT_MODE=1
```

> **Note:** Setting both `LIFI_AGENT_STRICT_MODE=1` and `LIFI_AGENT_MOCK_MODE=1` raises a conflict error.

Run `python -m lifi_agent doctor` to see the current mode, endpoint, and diagnostics.

### Setup

```bash
# Clone and build the MCP server
git clone https://github.com/lifinance/lifi-intents-mcp
cd lifi-intents-mcp
npm install
npm run build

# Run in stateless HTTP mode
PORT=3333 node dist/transport-http.js
```

The server starts at `http://localhost:3333/mcp`. This is already the default URL in this project (`LIFI_MCP_URL` env var).

**Why run locally?** The hosted version uses session management that can cause "No valid session ID" errors. The local stateless mode avoids this entirely.

**Note:** The solver network may be temporarily offline, causing all quotes to return empty. This is not a bug — it's a known transient state.

---

## Quick start

```bash
git clone https://github.com/tiyadegure/lifi-intents-demo.git
cd lifi-intents-demo

python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# CLI
python -m lifi_agent

# Web UI
python -m lifi_agent.server
# → http://localhost:8888

# Doctor
python -m lifi_agent doctor
```

---

## CLI examples

```
# Safe Verdict (with decision trace)
> safe send 10 USDC from Base to Arbitrum if fee < 0.5%

# Solver-aware route check
> solver base arbitrum USDC USDC

# Compare quotes across chains
> compare 50 USDC from Base

# Route health
> route health base arbitrum

# Quote history
> stats
```

---

## Project structure

```
lifi_agent/
├── agent.py        # Intent parser, policy engine, safe verdict, doctor
├── mcp_client.py   # LI.FI Intents MCP client (SSE transport)
├── server.py       # Web UI (FastAPI + inline HTML)
└── __main__.py     # CLI entry point

PITFALLS.md         # 10 LI.FI Intents MCP pitfalls I hit while building this
```

---

## Why this matters

LI.FI Intents MCP is a new protocol. Most developers will hit the same issues I did — SSE responses, session management, token address mapping, amount unit conversion.

This project is both a **working demo** and a **developer reference**:
- The code shows how to correctly integrate with LI.FI Intents MCP
- PITFALLS.md documents the hard-won lessons
- The Doctor tool helps others debug their own integrations

---

## Links

- **Live demo**: [lifi.degure.me](http://lifi.degure.me)
- **GitHub**: [tiyadegure/lifi-intents-demo](https://github.com/tiyadegure/lifi-intents-demo)
- **LI.FI Intents docs**: [docs.li.fi/lifi-intents](https://docs.li.fi/lifi-intents/introduction)
- **PITFALLS.md**: [10 pitfalls](PITFALLS.md)

---

Built for the [LI.FI Intents Mini Builder Challenge](https://lifi.notion.site/LI-FI-Intents-Mini-Builder-Challenge-366f0ff14ac78168a0cdd9f44a3c1f13).

MIT
