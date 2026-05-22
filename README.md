# LI.FI Intents × AI Agent

> Cross-chain operations via natural language · Built for the [LI.FI Intents Builder Challenge](https://lifi.notion.site/LI-FI-Intents-Mini-Builder-Challenge-366f0ff14ac78168a0cdd9f44a3c1f13)

## ✨ Features

- **Natural Language Intents** — `send 10 USDC base->arb`, `bridge 50 USDC eth to poly`
- **MCP Integration** — Real-time quotes via LI.FI Intents MCP Server
- **Web UI** — Dark-themed dashboard with quote comparison, solver analytics, and transaction tracking
- **Rich CLI** — Auto-completion, color-coded output, interactive prompts
- **SQLite Persistence** — Quote history survives across sessions
- **Smart Retry** — Exponential backoff with rate limiting
- **Async Support** — Parallel quote fetching for faster comparisons

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/tiyadegure/lifi-intents-demo
cd lifi-intents-demo

# Install
pip install -e .

# Run CLI
python -m lifi_agent

# Start Web UI
uvicorn lifi_agent.server:app --port 8888
```

## 📖 Usage

### CLI Commands

| Command | Description |
|---------|-------------|
| `send 10 USDC base->arb` | Execute a cross-chain transfer |
| `compare 50 USDC from Ethereum` | Compare quotes across chains |
| `routes` | Show supported routes |
| `orders` | Show recent orders |
| `favorites` | Show saved routes |
| `history` | Show recent quotes (SQLite) |
| `stats` | Show quote statistics |
| `wallet` | Show demo wallet info |
| `quit` | Exit |

### Input Formats

```
send 10 USDC from Base to Arbitrum
bridge 50 USDC eth to poly
transfer 100 USDC base->arb
10 USDC base→arbitrum
```

## 🏗️ Architecture

```
User Input → Intent Parser → AI Agent → MCP Client → LI.FI MCP Server
                ↓                              ↓
           Chain Aliases              Rate Limiting + Cache
                ↓                              ↓
           Rich CLI/Web UI ←──── Quote Results + Analytics
```

### Components

- **Intent Parser** — NL to structured intents with chain aliases
- **MCP Client** — Session management, caching, retry, async support
- **AI Agent** — Quote orchestration, history tracking, preferences
- **Web UI** — FastAPI + vanilla JS, dark navy theme
- **CLI** — Rich + prompt_toolkit, auto-completion

## 🎨 Web UI

The Web UI includes:

- **Quote Result** — Real-time quotes with fee calculation
- **Route Comparison** — Multi-chain comparison with best route highlighting
- **Agent Reasoning** — Step-by-step MCP call visualization
- **Solver Network** — Active solver cards with chain coverage
- **Solver Analytics** — Stats cards + chain distribution chart
- **Transaction Tracker** — Order status timeline with auto-refresh
- **Quote Statistics** — Total quotes, average fee, top routes/tokens

## 🔧 Technical Highlights

### MCP Client
- Exponential backoff retry (2s, 4s, 8s)
- Rate limiting (min 1s between calls)
- Connection pooling (lazy-init clients)
- 5-minute response caching
- Async support with `call_async()`

### Agent
- SQLite persistence for quote history
- Chain alias resolution (arb, poly, op, avax)
- Arrow syntax support (base->arb, eth→poly)
- Multi-criteria route comparison
- Preference memory (favorite routes)

### CLI
- Rich panels and tables
- Color-coded chain names
- Fee color coding (green <0.2%, yellow <0.5%, red ≥0.5%)
- prompt_toolkit auto-completion
- Progress spinners during API calls

## 📦 SDK

Install as a Python package:

```bash
pip install lifi-agent
```

Use in your code:

```python
from lifi_agent import LifAgent, parse_intent

agent = LifAgent()
agent.connect()

intent = parse_intent("send 10 USDC base->arb")
result = agent.get_quote(intent)
print(result)
```

## 🛠️ Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Start dev server
uvicorn lifi_agent.server:app --reload --port 8888
```

## 📝 License

MIT

## 🙏 Acknowledgments

- [LI.FI](https://li.fi) for the Intents MCP Server
- [Model Context Protocol](https://modelcontextprotocol.io) for the spec
- [Rich](https://rich.readthedocs.io/) for terminal formatting
- [FastAPI](https://fastapi.tiangolo.com/) for the web framework

---

*Built for the LI.FI Intents Builder Challenge*
