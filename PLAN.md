# LI.FI Intents Demo — 4-Module Enhancement Plan

## Overview
4 tasks to complete in order. All changes in `/root/lifi-intents-demo`.

---

## Task 1: Stabilize Running Modes

**Goal**: Make Local MCP / Mock Mode / Strict Mode completely distinct and visible everywhere.

### Current issues:
- `_is_mock_forced()` is called directly in `connect()`, `call()`, `_init_session_sync()`, `_init_session_async()` — should only be checked once at init
- `mock_mode_source()` has a bug: checks `is_strict_mode()` after already confirming `is_mock_mode()`, returning "LIFI_AGENT_STRICT_MODE=1 violation" which is unreachable in normal flow (strict+mock raises RuntimeError)
- Web UI `ensure_connected()` doesn't show mode info to the user

### Changes needed in `mcp_client.py`:
1. In `__init__()`, check `_is_mock_forced()` ONCE and set `self._mock_mode = True` if forced
2. Remove redundant `_is_mock_forced()` checks from `connect()`, `call()`, `_init_session_*()` — they already check `self._mock_mode`
3. Add a `mode` property that returns a clear string: `"local_mcp"`, `"mock_forced"`, `"mock_fallback"`, `"strict"`
4. Fix `mock_mode_source()`: remove the unreachable `is_strict_mode()` branch
5. In `connect()`, if `is_strict_mode()` and `_is_mock_forced()`, raise immediately (already done, keep it)

### Changes needed in `server.py`:
1. Add `/api/status` endpoint that returns: `{"mode": "...", "endpoint": "...", "connected": true/false, "mock_source": "..."}`
2. In `ensure_connected()`, print clearer mode message

### Changes needed in `agent.py` CLI:
- Already shows mode on connect. Just ensure it uses `self.mcp.mode` property.

---

## Task 2: Add Core Tests

**Goal**: Test the most critical logic paths, not everything.

### New test file: `tests/test_core_logic.py`

**Amount/Output Parsing tests** (from `models.py`):
- `raw_to_amount("9980000", "usdc")` → `9.98`
- `normalize_output_amount("9.98", "10", "usdc")` → `9.98` (human-readable)
- `normalize_output_amount("9980000", "10", "usdc")` → `9.98` (raw)
- `parse_amount_with_symbol("0.978879 USDC")` → `0.978879`
- Edge cases: `0`, empty string, no symbol

**Policy Parser tests** (from `parser.py`):
- `"send 10 USDC from Base to Arbitrum if fee < 0.5%"` → Policy with max_fee_pct=0.5
- `"send 10 USDC from Base to Arbitrum if output >= 9.9"` → min_output_amount=9.9
- `"send 10 USDC from Base to Arbitrum avoid Ethereum"` → avoid_chains=["ethereum"]
- `"send 10 USDC from Base to Arbitrum if healthy"` → require_healthy_route=True
- Combined: `"send 10 USDC from Base to Arbitrum if fee < 0.5% and healthy"`

**Safe Verdict tests** (using mock MCP):
- EXECUTABLE: 10 USDC Base→Arbitrum, no policy → should EXECUTE
- REFUSED (fee): 10 USDC Base→Arbitrum, fee < 0.01% → should REFUSE (mock fee is ~0.2%)
- REFUSED (avoid): send from Ethereum, avoid Ethereum → REFUSED
- REFUSED (min output): output >= 100 USDC on 10 USDC input → REFUSED

**Mock Mode behavior tests**:
- `LIFI_AGENT_MOCK_MODE=1` → `is_mock_mode()` True, `mode` == "mock_forced"
- Auto-fallback (bad port) → `is_mock_mode()` True, `mode` == "mock_fallback"
- Mock call returns consistent data structure

**Strict Mode tests**:
- `LIFI_AGENT_STRICT_MODE=1` + bad port → raises exception (no fallback)
- `LIFI_AGENT_STRICT_MODE=1` + `LIFI_AGENT_MOCK_MODE=1` → raises RuntimeError (conflict)

---

## Task 3: Polish Doctor

**Goal**: Upgrade from checklist to developer diagnostic report.

### Changes in `agent.py` `doctor()` method:

Restructure into clear groups with a summary section:

```
═══ LI.FI Intents MCP Doctor ═══

[Mode]
  Current Mode: local_mcp (or mock_forced, mock_fallback, strict)
  MCP Endpoint: http://localhost:3333/mcp
  Strict Mode: disabled
  Mock Source: (if applicable)

[Connection]
  ✓ MCP endpoint reachable: Connected to lifi-intents
  ✓ Session: Stateless mode (no session ID)

[Protocol]
  ✓ MCP Protocol: 2025-03-26, server: lifi-intents v1.0.0
  ✓ Tools Available: 9 tools: get-supported-routes, request-quote, ...

[Routes]
  ✓ get-supported-routes: 146 routes available
  ✓ Base USDC: 0x833589fC...
  ✓ Arbitrum USDC: 0xaf88d065...

[Quotes]
  ✓ request-quote: 1 USDC → 0.978694 USDC
  ✓ Quote Test: Base→Arbitrum solver responded

[Warnings]
  ! OPENAI_API_KEY not set: Using deterministic parser

[Next Action]
  → All checks passed. Try: python -m lifi_agent "send 10 USDC from Base to Arbitrum"
  OR: → Fix X, then retry doctor
```

Add `mode` group before Connection. Add `next_action` field to the report.

---

## Task 4: Enhance Web Experience

**Goal**: Add presets so users can try the demo without constructing prompts.

### Changes in `server.py`:
Add `/api/presets` endpoint returning a list of preset scenarios:
```json
[
  {"name": "Safe Transfer", "prompt": "send 10 USDC from Base to Arbitrum", "description": "Basic cross-chain USDC transfer"},
  {"name": "Fee Check", "prompt": "send 10 USDC from Base to Arbitrum if fee < 0.01%", "description": "Will be REFUSED — fee too high"},
  {"name": "Healthy Route", "prompt": "send 10 USDC from Base to Arbitrum if healthy", "description": "Requires route health check"},
  {"name": "Avoid Ethereum", "prompt": "send 10 USDC from Ethereum to Arbitrum avoid Ethereum", "description": "Will be REFUSED — source in avoid list"},
  {"name": "Min Output", "prompt": "send 10 USDC from Base to Arbitrum if output >= 9.99", "description": "Check minimum output constraint"}
]
```

Add `/api/verdict-trace` endpoint that returns the full DecisionResult trace as JSON (for the frontend to render step-by-step).

### Changes in `templates/index.html`:
- Add a presets section with clickable buttons
- Each preset fills the input and runs the verdict
- Show the decision trace as a step-by-step visual

---

## Execution Order
1. Task 1 (modes) — foundation for everything else
2. Task 2 (tests) — verify the logic works
3. Task 3 (doctor) — uses the new mode property
4. Task 4 (web) — uses presets and verdict trace

## Verification
After all tasks:
```bash
cd /root/lifi-intents-demo
python -m pytest tests/ -v --tb=short
python -m lifi_agent doctor
```

## Constraints
- Don't break existing tests (305 should still pass)
- Keep backward compatibility with existing CLI commands
- Mock mode data structure should stay consistent
- Chinese comments are fine, English for code/docs
