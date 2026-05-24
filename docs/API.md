# API Contract

LI.FI Intents Agent Web API reference. All endpoints return JSON.

Base URL: `http://localhost:8888`

---

## GET /api/status

Current operating mode and connection status.

**Response:**
```json
{
  "mode": "local_mcp" | "mock_forced" | "mock_fallback" | "strict",
  "endpoint": "http://localhost:3333/mcp",
  "connected": true,
  "mock_source": null | "LIFI_AGENT_MOCK_MODE=1" | "auto-fallback (local MCP unreachable)",
  "strict_mode": false
}
```

---

## GET /api/presets

List all demo presets with intent + policy config.

**Response:**
```json
{
  "presets": [
    {
      "name": "safe-transfer",
      "description": "Standard Base → Arbitrum USDC transfer with a 0.5% fee cap.",
      "intent": {
        "from_chain": "base",
        "to_chain": "arbitrum",
        "token": "USDC",
        "amount": "10"
      },
      "policy": {
        "max_fee_pct": 0.5,
        "require_healthy_route": false
      },
      "category": "success" | "failure",
      "expected_verdict": "EXECUTABLE" | "REFUSED"
    }
  ]
}
```

**Available presets:**
- `safe-transfer` — Basic transfer, fee < 0.5% → EXECUTABLE
- `fee-check` — Ethereum → Base, fee < 0.3% → EXECUTABLE
- `health-check` — Requires route health → REFUSED
- `avoid-chain` — Avoids Arbitrum (destination) → REFUSED
- `cheapest-route` — Prefers cheapest solver → EXECUTABLE
- `no-quote` — Unusual chain pair, graceful failure → REFUSED
- `strict-fee-check` — Fee < 0.1%, likely REFUSED
- `fee-too-high` — Fee < 0.01%, always REFUSED
- `min-output` — Output ≥ 9.99, edge-case REFUSED
- `multi-constraint` — Fee + avoid + min output combined → REFUSED

---

## GET /api/preset/{name}

Single preset by name.

**Path params:**
- `name` — preset slug (e.g. `safe-transfer`)

**Response:** Same as single preset object above, or 404 with error:
```json
{
  "error": true,
  "code": "PRESET_NOT_FOUND",
  "message": "Unknown preset: bad-name",
  "next_action": ["Available presets: safe-transfer, fee-check, ..."]
}
```

---

## POST /api/analyze-intent

Full Safe Verdict pipeline: parse intent → policy → MCP calls → decision trace.

**Request body:**
```json
{
  "text": "send 10 USDC from Base to Arbitrum only if fee < 0.5%"
}
```

**Response:**
```json
{
  "intent": {
    "amount": "10",
    "token": "USDC",
    "from_chain": "base",
    "to_chain": "arbitrum"
  },
  "policy": {
    "max_fee_pct": 0.5,
    "min_output_amount": null,
    "require_healthy_route": false,
    "allow_cross_chain": true,
    "avoid_chains": []
  },
  "quote_params": {
    "fromChain": "base",
    "toChain": "arbitrum",
    "fromToken": "USDC",
    "toToken": "USDC",
    "amount": "10"
  },
  "verdict": "EXECUTABLE" | "REFUSED",
  "reason": "This intent satisfies the user policy. Fee 0.20% is within acceptable limits.",
  "steps": [
    {
      "name": "Parse Intent",
      "status": "passed",
      "detail": "10 USDC base → arbitrum",
      "duration_ms": 0,
      "mcp_tool": "",
      "purpose": "Extract structured intent from natural language",
      "input_summary": "\"send 10 USDC from Base to Arbitrum\"",
      "output_summary": "amount=10, token=USDC, from=base, to=arbitrum",
      "why": "Natural language must be decomposed into chain IDs, token, and amount before any MCP call."
    },
    {
      "name": "Parse Policy",
      "status": "passed",
      "detail": "Policy(fee<0.5%)",
      "duration_ms": 0,
      "mcp_tool": "",
      "purpose": "Extract policy constraints from natural language",
      "input_summary": "\"send 10 USDC from Base to Arbitrum only if fee < 0.5%\"",
      "output_summary": "max_fee_pct=0.5",
      "why": "Policy constraints (fee limits, chain avoidance) are parsed from free text to enforce programmatically."
    },
    {
      "name": "Check Supported Route",
      "status": "passed",
      "detail": "base → arbitrum (USDC)",
      "duration_ms": 45,
      "mcp_tool": "get-supported-routes",
      "purpose": "Verify route exists in LI.FI network",
      "input_summary": "from_chain=base, to_chain=arbitrum, token=USDC",
      "output_summary": "146 routes found",
      "why": "If no solver supports this chain pair, the transfer cannot proceed regardless of quote."
    },
    {
      "name": "Get Quote",
      "status": "passed",
      "detail": "Output: 9.980000 USDC, Quote ID: abc123...",
      "duration_ms": 320,
      "mcp_tool": "request-quote",
      "purpose": "Request real-time solver quote from LI.FI network",
      "input_summary": "fromChain=base, toChain=arbitrum, fromToken=USDC, toToken=USDC, amount=10",
      "output_summary": "output=9.980000 USDC, quoteId=abc123...",
      "why": "The quote determines the actual output amount and fee, which policy constraints are evaluated against."
    },
    {
      "name": "Calculate Fee",
      "status": "passed",
      "detail": "Fee: 0.20%",
      "duration_ms": 0,
      "mcp_tool": "",
      "purpose": "Compute transfer fee percentage",
      "input_summary": "input=10, output=9.980000",
      "output_summary": "Fee: 0.20%",
      "why": "Fee = (input - output) / input * 100. This derived value drives the fee policy check."
    },
    {
      "name": "Fee Policy",
      "status": "passed",
      "detail": "Fee 0.20% ≤ limit 0.5%",
      "duration_ms": 0,
      "mcp_tool": "",
      "purpose": "Enforce user-defined fee constraint",
      "input_summary": "actual=0.20, threshold=0.5",
      "output_summary": "Fee 0.20% ≤ limit 0.5%",
      "why": "Compares calculated fee against the user's max_fee_pct limit to decide EXECUTABLE vs REFUSED."
    }
  ],
  "total_duration_ms": 365
}
```

**Key fields:**
- `verdict` — `"EXECUTABLE"` or `"REFUSED"`. The final decision.
- `reason` — Human-readable explanation of why.
- `steps[]` — Decision trace (MCP Call Inspector).
- `steps[].mcp_tool` — Which MCP tool was called (empty string for policy-only steps).
- `steps[].purpose` — Why this step exists.
- `steps[].input_summary` — Key parameters sent to MCP tool.
- `steps[].output_summary` — Key results returned.
- `steps[].why` — Educational explanation of why this step matters.

**Error response:**
```json
{
  "error": true,
  "code": "MISSING_INPUT" | "INVALID_CHAIN" | "INVALID_TOKEN" | "INVALID_AMOUNT" | "QUOTE_ERROR" | "PARSE_ERROR" | "VERDICT_ERROR",
  "message": "No intent text provided",
  "next_action": "Provide intent in 'text' field"
}
```

---

## GET /api/judge-mode

Run 5 key presets sequentially and compare expected vs actual verdict.

**Response:**
```json
{
  "results": [
    {
      "step_num": 1,
      "preset_name": "safe-transfer",
      "description": "Standard Base → Arbitrum USDC transfer with a 0.5% fee cap.",
      "expected_verdict": "EXECUTABLE",
      "actual_verdict": "EXECUTABLE",
      "match": true,
      "reason": "This intent satisfies the user policy."
    },
    {
      "step_num": 5,
      "preset_name": "doctor",
      "description": "Run diagnostic checks on MCP connection",
      "expected_verdict": "PASS",
      "actual_verdict": "PASS",
      "match": true,
      "reason": "Mode: local_mcp, Endpoint: http://localhost:3333/mcp",
      "critical_failures": [],
      "warnings": ["OPENAI_API_KEY not set: Using deterministic parser (no LLM fallback)"]
    }
  ]
}
```

**Doctor step details:**
- `critical_failures[]` — MCP endpoint unreachable, session failed, protocol mismatch, no tools
- `warnings[]` — Non-critical issues like missing API keys
- `actual_verdict` — `"FAIL"` if any critical failures, `"PASS"` if only warnings

---

## GET /api/preset-report

Run ALL 10 presets and compare expected vs actual verdict.

**Response:**
```json
{
  "results": [
    {
      "name": "safe-transfer",
      "expected": "EXECUTABLE",
      "actual": "EXECUTABLE",
      "match": true,
      "reason": "This intent satisfies the user policy."
    }
  ],
  "summary": {
    "total": 10,
    "matched": 10,
    "mismatched": 0
  }
}
```

---

## GET /api/mcp-proof

Prove the project uses real MCP connections by running a live quote.

**Response:**
```json
{
  "mode": "local_mcp",
  "real_mcp": true,
  "mcp_server": "LI.FI Intents MCP",
  "endpoint": "http://localhost:3333/mcp",
  "routes_count": 146,
  "last_quote": {
    "route": "Base → Arbitrum",
    "input": "1 USDC",
    "output": "0.978703 USDC",
    "fee_pct": "2.13",
    "verdict": "EXECUTABLE",
    "timestamp": 1779591709.35
  }
}
```

**Key fields:**
- `real_mcp` — `true` when mode is `local_mcp` or `strict` (real MCP server). `false` for mock modes.
- `last_quote` — Live quote from real solver network (or error if MCP unreachable).

---

## GET /api/doctor

Same as CLI `doctor` command.

**Response:**
```json
{
  "groups": [
    {
      "name": "Mode",
      "checks": [
        {"name": "Current Mode", "passed": true, "detail": "local_mcp"},
        {"name": "MCP Endpoint", "passed": true, "detail": "http://localhost:3333/mcp"},
        {"name": "Strict Mode", "passed": true, "detail": "disabled"}
      ]
    }
  ],
  "warnings": [],
  "mode": "local_mcp",
  "endpoint": "http://localhost:3333/mcp",
  "next_action": "All checks passed. Try: python -m lifi_agent \"send 10 USDC from Base to Arbitrum\""
}
```

---

## Other endpoints

- `GET /api/routes` — All supported chain pairs
- `GET /api/quote?from_chain=base&to_chain=arbitrum&token=usdc&amount=10` — Single quote
- `GET /api/compare?from_chain=base&token=usdc&amount=10` — Compare quotes across chains
- `GET /api/solvers` — List solver identities
- `GET /api/solver-stats` — Aggregated solver stats
- `GET /api/route-health?from_chain=base&to_chain=arbitrum` — Route health check
- `GET /api/traces` — Recent reasoning traces (last 20)
- `GET /api/stats` — Quote statistics
- `GET /api/favorites` — Saved routes
