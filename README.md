# LI.FI Intents × AI Agent — Safe Verdict Playground

> Policy-driven cross-chain decisions for AI Agents.
> Turn natural language into EXECUTABLE or REFUSED verdicts with full decision traces.

**🔗 Live demo → [lifi.degure.me](https://lifi.degure.me)**

Built for the [LI.FI Intents Mini Builder Challenge](https://lifi.notion.site/LI-FI-Intents-Mini-Builder-Challenge-366f0ff14ac78168a0cdd9f44a3c1f13).

---

## What it does

Type a natural language cross-chain intent with safety constraints:

```
send 0.001 WETH from Base to Arbitrum only if route is healthy and fee < 0.5%
```

The system:

1. **Parses** your intent into structured parameters (amount, token, chains)
2. **Extracts policy** constraints (max fee, route health requirement)
3. **Calls LI.FI MCP tools** (get-supported-routes, check-route-health, request-quote)
4. **Runs a decision trace** — every check logged with timing and tool names
5. **Returns a verdict**: ✅ EXECUTABLE or 🚫 REFUSED with reasoning

---

## Screenshots

### Web Interface — Homepage
![Homepage](remotion/public/recordings/ui-homepage.png)

### Decision Trace — EXECUTABLE
![Executable](remotion/public/recordings/ui-result-executable.png)

### MCP Proof — Real Server Connection
![MCP Proof](remotion/public/recordings/ui-mcp-proof.png)

---

## Features

| Feature | Description |
|---------|-------------|
| 🛡️ **Safe Verdict** | Policy-driven EXECUTABLE / REFUSED decisions |
| 📊 **Decision Trace** | Step-by-step audit log with MCP tool names and timing |
| 🔌 **MCP Integration** | Real connection to LI.FI Intents MCP server |
| 🎯 **10 Policy Presets** | One-click testing: safe-transfer, fee-check, health-check, etc. |
| 🌐 **Web UI** | Three-column layout: Intent → Structured Output → Decision Trace |
| 💻 **CLI** | Interactive terminal with rich formatting |
| 🔍 **MCP Proof** | Live server connection verification with route count and quote data |
| 🧪 **366 Tests** | Full test coverage for parser, policies, verdicts, and API |

---

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐     ┌──────────────┐
│  User Goal  │ ──→ │  AI Agent   │ ──→ │   MCP Server    │ ──→ │   Solver     │
│  (natural   │     │  (parse +   │     │  (LI.FI Intents │     │   Network    │
│  language)  │     │   policy)   │     │   API)          │     │  (compete)   │
└─────────────┘     └─────────────┘     └─────────────────┘     └──────────────┘
                                                                       │
                                                                       ↓
                                                              ┌──────────────┐
                                                              │ Safe Verdict │
                                                              │ EXECUTABLE   │
                                                              │ or REFUSED   │
                                                              └──────────────┘
```

### MCP Tools Used

- `get-supported-routes` — Discover available cross-chain routes
- `check-route-health` — Verify solver coverage and recent order activity
- `request-quote` — Get real-time solver quotes
- `prepare-order` — Build order structure for execution
- `track-order` — Monitor order status

---

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+ (for Web UI)

### Install

```bash
git clone https://github.com/tiyadegure/lifi-intents-demo.git
cd lifi-intents-demo
pip install -e .
```

### Run CLI

```bash
python -m lifi_agent
# or
lifi-agent
```

### Run Web UI

```bash
cd demo
npm install
npm run dev
# Open http://localhost:8888
```

### Run Tests

```bash
pytest tests/ -v
# 366 tests, all passing
```

---

## Project Structure

```
lifi-intents-demo/
├── lifi_agent/          # Core Python package
│   ├── parser.py        # Intent parser (regex + LLM fallback)
│   ├── policy.py        # Policy engine (fee, health, chain constraints)
│   ├── verdict.py       # Decision engine (EXECUTABLE / REFUSED)
│   ├── mcp_client.py    # MCP server client
│   └── cli.py           # Interactive CLI
├── demo/                # Web UI (Next.js)
├── tests/               # 366 tests
├── docs/                # API reference, failure modes
├── PITFALLS.md          # 10 real pitfalls building against LI.FI Intents
└── remotion/            # Demo video source
```

---

## Key Design Decisions

1. **Deterministic parser by default** — regex engine, zero API keys, consistent output
2. **Policy-first architecture** — constraints extracted before any MCP calls
3. **Visible decision trace** — every step logged with tool name, timing, and result
4. **Three-mode MCP** — Local MCP (default) → Mock Fallback → Mock Forced → Strict
5. **No real wallet execution** — this is a decision engine, not a transaction executor

---

## Documentation

- [API Reference](docs/API.md) — All endpoints and response formats
- [Failure Modes](docs/FAILURE-MODES.md) — How the system handles errors
- [Pitfalls](PITFALLS.md) — 10 real pitfalls encountered building against LI.FI Intents MCP

---

## License

MIT

---

Built with ❤️ for the LI.FI Intents Builder Challenge
