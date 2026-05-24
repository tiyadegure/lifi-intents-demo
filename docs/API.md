# API Contract

LI.FI Intents Agent Web API reference. All endpoints return JSON.

Base URL: `http://localhost:8888`

---

## GET /api/status

Current operating mode and connection status.

**Response:**
```
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
```
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
      "category": "success" | "failure" | "edge-case"
    }
  ]
}
```

**Available presets:**
- `safe-transfer` — Basic transfer, fee < 0.5%
- `fee-check` — Ethereum → Base, fee < 0.3%
- `health-check` — Requires route health
- `avoid-chain` — Avoids Arbitrum (destination) → REFUSED
- `cheapest-route` — Prefers cheapest solver
- `no-quote` — Unusual chain pair, graceful failure
- `strict-fee-check` — Fee < 0.1%, likely REFUSED
- `fee-too-high` — Fee < 0.01%, always REFUSED
- `min-output` — Output ≥ 9.99, edge-case REFUSED
- `multi-constraint` — Fee + avoid + min output combined

---

## GET /api/preset/{name}

Single preset by name.

**Path params:**
- `name` — preset slug (e.g. `safe-transfer`)

**Response:** Same as single preset object above, or 404 with available list.

---

## POST /api/analyze-intent

Full Safe Verdict pipeline: parse intent → policy → MCP calls → decision trace.

**Request body:**
```
{
  "text": "send 10 USDC from Base to Arbitrum only if fee < 0.5%"
}
```

**Response:**
```
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
      "mcp_tool": null
    },
    {
      "name": "Check Supported Route",
      "status": "passed",
      "detail": "base → arbitrum (USDC)",
      "duration_ms": 45,
      "mcp_tool": "get-supported-routes"
    },
    {
      "name": "Get Quote",
      "status": "passed",
      "detail": "Output: 9.980000 USDC, Quote ID: abc123...",
      "duration_ms": 320,
      "mcp_tool": "request-quote"
    },
    {
      "name": "Fee Policy",
      "status": "passed",
      "detail": "Fee 0.20% ≤ limit 0.5%",
      "duration_ms": 0,
      "mcp_tool": null
    }
  ],
  "total_duration_ms": 365
}
```

**Key fields:**
- `verdict` — `"EXECUTABLE"` or `"REFUSED"`. The final decision.
- `reason` — Human-readable explanation of why.
- `steps[]` — Decision trace. Each step has `name`, `status` (`passed`/`failed`/`skipped`), `detail`, `duration_ms`.
- `steps[].mcp_tool` — Which MCP tool was called (`null` for policy-only steps).

---

## GET /api/doctor

Same as CLI `doctor` command.

**Response:**
```
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
