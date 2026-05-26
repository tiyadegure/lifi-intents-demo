"""LI.FI Intents Agent — Web API server."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path
import asyncio
import collections
import dataclasses
import html as html_mod
import json
import os
import threading
import time

from lifi_agent.agent import LifAgent, Intent, parse_intent, parse_intent_with_policy
from lifi_agent.models import Policy


@asynccontextmanager
async def lifespan(app):
    # MCP connects lazily on first request
    yield


app = FastAPI(title="LI.FI Intents Agent", version="1.0.0", lifespan=lifespan)
agent = LifAgent()

# ── Reasoning trace storage ─────────────────────────────────────────
traces = collections.deque(maxlen=200)
traces_lock = threading.Lock()
_connect_lock = threading.Lock()


def _escape_html(value: str) -> str:
    """Escape a string for safe insertion into HTML."""
    return html_mod.escape(str(value), quote=True)


def _error_response(code: str, message: str, status_code: int = 400, next_action: str = ""):
    """Return a unified error JSON response."""
    body = {"error": True, "code": code, "message": message}
    if next_action:
        body["next_action"] = next_action
    return JSONResponse(body, status_code=status_code)


def trace_step(tool: str, args: dict, result: dict, duration_ms: int):
    """Record an agent reasoning step."""
    step = {
        "timestamp": time.time(),
        "tool": tool,
        "args": args,
        "result_summary": _summarize_result(result),
        "duration_ms": duration_ms,
    }
    with traces_lock:
        traces.append(step)
    return step


def _summarize_result(result: dict) -> str:
    if "error" in result:
        return f"Error: {result['error'][:100]}"
    if "data" in result:
        data = result["data"]
        if "quotes" in data:
            q = data["quotes"][0] if data["quotes"] else {}
            return f"Quote: {q.get('inputAmount', '?')} → {q.get('outputAmount', '?')}"
        if "count" in data:
            return f"{data['count']} routes found"
    return json.dumps(result)[:100]


# ── API Routes ──────────────────────────────────────────────────────

def ensure_connected():
    """Lazy MCP connection (auto-fallback to mock mode if local MCP unavailable)."""
    if not agent.mcp._connected:
        with _connect_lock:
            if not agent.mcp._connected:
                try:
                    agent.connect()
                    if agent.mcp.is_mock_mode():
                        print("MCP: local server not available, using mock mode")
                    else:
                        print("MCP: connected to local server")
                except Exception as e:
                    print(f"MCP connect failed: {e}")


@app.get("/api/routes")
async def get_routes():
    await asyncio.to_thread(ensure_connected)
    start = time.time()
    result = await asyncio.to_thread(agent.get_routes)
    duration = int((time.time() - start) * 1000)
    trace_step("get-supported-routes", {}, result, duration)
    return result


@app.get("/api/status")
async def get_status():
    """Return current operating mode and connection status."""
    await asyncio.to_thread(ensure_connected)
    return {
        "mode": agent.mcp.mode,
        "endpoint": agent.mcp.url,
        "connected": agent.mcp._connected,
        "mock_source": agent.mcp.mock_mode_source() or None,
        "strict_mode": agent.mcp.is_strict_mode(),
    }


@app.get("/api/doctor")
async def doctor():
    """Run diagnostic checks and return developer report."""
    await asyncio.to_thread(ensure_connected)
    report = await asyncio.to_thread(agent.doctor)
    return report


@app.get("/api/quote")
async def get_quote(from_chain: str, to_chain: str, token: str, amount: str):
    # Input validation
    valid_chains = {"ethereum", "base", "arbitrum", "optimism", "polygon", "bsc", "avalanche", "zksync", "linea", "scroll", "blast", "mantle", "sonic"}
    valid_tokens = {"usdc", "usdt", "eth", "weth"}
    if from_chain.lower() not in valid_chains:
        return _error_response("INVALID_CHAIN", f"Invalid from_chain: {from_chain}", 400, "Valid chains: " + ", ".join(sorted(valid_chains)))
    if to_chain.lower() not in valid_chains:
        return _error_response("INVALID_CHAIN", f"Invalid to_chain: {to_chain}", 400, "Valid chains: " + ", ".join(sorted(valid_chains)))
    if token.lower() not in valid_tokens:
        return _error_response("INVALID_TOKEN", f"Invalid token: {token}", 400, "Valid tokens: " + ", ".join(sorted(valid_tokens)))
    try:
        float(amount)
    except ValueError:
        return _error_response("INVALID_AMOUNT", f"Invalid amount: {amount}", 400, "Amount must be a number")

    await asyncio.to_thread(ensure_connected)
    start = time.time()
    try:
        intent = await asyncio.to_thread(
            parse_intent, f"send {amount} {token} from {from_chain} to {to_chain}"
        )
        result = await asyncio.to_thread(agent.get_quote, intent)
    except ValueError as e:
        return _error_response("QUOTE_ERROR", str(e), 400)
    duration = int((time.time() - start) * 1000)
    trace_step("request-quote", {
        "from": from_chain, "to": to_chain, "token": token, "amount": amount
    }, result, duration)
    return result


@app.get("/api/compare")
async def compare_quotes(from_chain: str, token: str, amount: str):
    await asyncio.to_thread(ensure_connected)
    start = time.time()
    try:
        intent = await asyncio.to_thread(
            parse_intent, f"send {amount} {token} from {from_chain} to ethereum"
        )
        results = await asyncio.to_thread(agent.compare_quotes, intent)
    except ValueError as e:
        return _error_response("COMPARE_ERROR", str(e), 400)
    duration = int((time.time() - start) * 1000)
    trace_step("compare-quotes", {
        "from": from_chain, "token": token, "amount": amount
    }, {"data": results}, duration)
    return {"data": results}


@app.get("/api/traces")
async def get_traces():
    with traces_lock:
        return {"traces": list(traces)[-20:]}


@app.get("/api/favorites")
async def get_favorites():
    return {"favorites": agent.get_favorite_routes()}


@app.get("/api/solvers")
async def get_solvers():
    await asyncio.to_thread(ensure_connected)
    start = time.time()
    result = await asyncio.to_thread(agent.get_solver_identities)
    duration = int((time.time() - start) * 1000)
    trace_step("get-solver-identities", {}, result, duration)
    return result


def _collect_solver_stats() -> dict:
    """Collect solver statistics (runs in thread)."""
    ensure_connected()
    start = time.time()
    solvers_result = agent.get_solver_identities()
    identities = solvers_result.get("data", {}).get("solverIdentities",
                 solvers_result.get("data", {}).get("solvers", []))

    total_solvers = len(identities)
    active_solvers = 0
    total_routes = 0
    total_response_ms = 0
    checked = 0
    chain_counts: dict[str, int] = {}

    routes_result = agent.get_routes()
    route_list = routes_result.get("data", {}).get("routes", [])
    seen_pairs: set[tuple[int, int]] = set()
    sample_routes = []
    for r in route_list:
        pair = (r.get("fromChainId", 0), r.get("toChainId", 0))
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            sample_routes.append(r)
    sample_routes = sample_routes[:20]

    for r in sample_routes:
        from_id = str(r.get("fromChainId", ""))
        to_id = str(r.get("toChainId", ""))
        from_name = r.get("fromChain", from_id) if isinstance(r.get("fromChain"), str) else r.get("fromChain", {}).get("name", from_id)
        to_name = r.get("toChain", to_id) if isinstance(r.get("toChain"), str) else r.get("toChain", {}).get("name", to_id)
        try:
            t0 = time.time()
            health = agent.check_route_health(from_id, to_id)
            elapsed = int((time.time() - t0) * 1000)
            total_response_ms += elapsed
            checked += 1
            is_healthy = health.get("data", {}).get("healthy", True)
            if is_healthy:
                total_routes += 1
            chain_counts[from_name] = chain_counts.get(from_name, 0) + 1
            chain_counts[to_name] = chain_counts.get(to_name, 0) + 1
        except Exception:
            continue

    active_solvers = min(total_solvers, max(1, total_routes)) if total_solvers > 0 else 0
    if not chain_counts and identities:
        for s in identities:
            for ch in (s.get("supportedChains") or s.get("chains") or []):
                chain_counts[ch] = chain_counts.get(ch, 0) + 1

    avg_response = (total_response_ms // checked) if checked > 0 else 0
    duration = int((time.time() - start) * 1000)
    trace_step("solver-stats", {}, {"total": total_solvers, "active": active_solvers}, duration)

    return {
        "totalSolvers": total_solvers,
        "activeSolvers": active_solvers,
        "routesCovered": total_routes,
        "avgResponseTime": avg_response,
        "chainDistribution": chain_counts,
    }


@app.get("/api/solver-stats")
async def get_solver_stats():
    return await asyncio.to_thread(_collect_solver_stats)


@app.get("/api/track-order")
async def track_order(order_id: str):
    await asyncio.to_thread(ensure_connected)
    start = time.time()
    result = await asyncio.to_thread(agent.track_order, order_id)
    duration = int((time.time() - start) * 1000)
    trace_step("track-order", {"orderId": order_id}, result, duration)
    return result


@app.get("/api/recent-orders")
async def recent_orders():
    await asyncio.to_thread(ensure_connected)
    start = time.time()
    result = await asyncio.to_thread(agent.list_orders, 5)
    duration = int((time.time() - start) * 1000)
    trace_step("list-orders", {"limit": 5}, result, duration)
    return result


@app.get("/api/stats")
async def get_stats():
    from lifi_agent.agent import get_quote_store
    return get_quote_store().get_stats()


@app.get("/api/solver-inventory")
async def solver_inventory(from_chain: str, to_chain: str, from_asset: str, to_asset: str):
    await asyncio.to_thread(ensure_connected)
    start = time.time()
    result = await asyncio.to_thread(agent.get_quote_inventory, from_chain, to_chain, from_asset, to_asset)
    duration = int((time.time() - start) * 1000)
    trace_step("get-quote-inventory", {
        "from_chain": from_chain, "to_chain": to_chain,
        "from_asset": from_asset, "to_asset": to_asset,
    }, result, duration)
    return result


@app.get("/api/route-health")
async def route_health(from_chain: str, to_chain: str):
    await asyncio.to_thread(ensure_connected)
    start = time.time()
    result = await asyncio.to_thread(agent.check_route_health, from_chain, to_chain)
    duration = int((time.time() - start) * 1000)
    trace_step("check-route-health", {"from_chain": from_chain, "to_chain": to_chain}, result, duration)
    return result


# ── Presets ──────────────────────────────────────────────────────────

PRESETS = {
    "safe-transfer": {
        "intent": {"from_chain": "base", "to_chain": "arbitrum", "token": "USDC", "amount": "10"},
        "policy": {"max_fee_pct": 2.0, "require_healthy_route": False},
        "description": "Standard Base → Arbitrum USDC transfer with a 2% fee cap.",
        "category": "success",
        "expected_verdict": "EXECUTABLE",
    },
    "fee-check": {
        "intent": {"from_chain": "base", "to_chain": "arbitrum", "token": "USDC", "amount": "10"},
        "policy": {"max_fee_pct": 2.0},
        "description": "Base → Arbitrum USDC transfer with 2% fee limit — tests fee policy.",
        "category": "success",
        "expected_verdict": "EXECUTABLE",
    },
    "health-check": {
        "intent": {"from_chain": "base", "to_chain": "arbitrum", "token": "USDC", "amount": "10"},
        "policy": {"require_healthy_route": True},
        "description": "Route health enforcement — refuses if solvers report unhealthy.",
        "category": "failure",
        "expected_verdict": "REFUSED",
    },
    "avoid-chain": {
        "intent": {"from_chain": "base", "to_chain": "arbitrum", "token": "USDC", "amount": "10"},
        "policy": {"avoid_chains": ["arbitrum"], "max_fee_pct": 2.0},
        "description": "Sends to Arbitrum but policy avoids Arbitrum — should be REFUSED.",
        "category": "failure",
        "expected_verdict": "REFUSED",
    },
    "cheapest-route": {
        "intent": {"from_chain": "base", "to_chain": "arbitrum", "token": "USDC", "amount": "10"},
        "policy": {"prefer_cheapest": True, "max_fee_pct": 2.0},
        "description": "Prefers the cheapest route with a 2% fee ceiling.",
        "category": "success",
        "expected_verdict": "EXECUTABLE",
    },
    "no-quote": {
        "intent": {"from_chain": "base", "to_chain": "zksync", "token": "USDC", "amount": "5"},
        "policy": {"require_quote": True, "max_fee_pct": 0.5},
        "description": "Tests an unsupported chain pair — expected to fail gracefully with no-quote handling.",
        "category": "failure",
        "expected_verdict": "REFUSED",
    },
    "strict-fee-check": {
        "intent": {"from_chain": "base", "to_chain": "arbitrum", "token": "USDC", "amount": "10"},
        "policy": {"max_fee_pct": 0.1},
        "description": "Fee limit set to 0.1% — likely to fail since solver fees are typically ~1%.",
        "category": "failure",
        "expected_verdict": "REFUSED",
    },
    "fee-too-high": {
        "intent": {"from_chain": "base", "to_chain": "arbitrum", "token": "USDC", "amount": "10"},
        "policy": {"max_fee_pct": 0.01},
        "description": "Fee limit set to 0.01% — always REFUSED.",
        "category": "failure",
        "expected_verdict": "REFUSED",
    },
    "min-output": {
        "intent": {"from_chain": "base", "to_chain": "arbitrum", "token": "USDC", "amount": "10"},
        "policy": {"min_output_amount": 9999},
        "description": "Requires minimum output of 9999 USDC — edge-case REFUSED.",
        "category": "failure",
        "expected_verdict": "REFUSED",
    },
    "multi-constraint": {
        "intent": {"from_chain": "base", "to_chain": "arbitrum", "token": "USDC", "amount": "10"},
        "policy": {"max_fee_pct": 2.0, "avoid_chains": ["ethereum", "polygon"], "min_output_amount": 9999},
        "description": "Combines fee cap, avoid chains, and minimum output — tests multiple policy checks at once.",
        "category": "failure",
        "expected_verdict": "REFUSED",
    },
}


@app.get("/api/presets")
async def list_presets():
    """List all available demo presets."""
    return {
        "presets": [
            {"name": name, "description": p["description"], "intent": p["intent"], "policy": p["policy"], "category": p.get("category", "success"), "expected_verdict": p.get("expected_verdict", "EXECUTABLE")}
            for name, p in PRESETS.items()
        ]
    }


@app.get("/api/preset/{name}")
async def get_preset(name: str):
    """Return a pre-configured intent + policy for a demo scenario."""
    preset = PRESETS.get(name)
    if not preset:
        return JSONResponse(
            {"error": True, "code": "PRESET_NOT_FOUND", "message": f"Unknown preset: {name}", "next_action": list(PRESETS.keys())},
            status_code=404,
        )
    return preset


@app.post("/api/explain")
async def explain_intent(request: Request):
    """Explain intent without executing — shows parsed intent, policy, and execution plan."""
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return _error_response("MISSING_INPUT", "No intent text provided", 400, "Provide intent in 'text' field")
    
    try:
        result = await asyncio.to_thread(agent.explain, text)
        return result
    except Exception as e:
        return _error_response("EXPLAIN_ERROR", str(e), 400)


@app.post("/api/analyze-intent")
async def analyze_intent(request: Request):
    """Full Safe Verdict analysis: parse intent → policy → MCP calls → decision trace."""
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return _error_response("MISSING_INPUT", "No intent text provided", 400, "Provide intent in 'text' field")

    await asyncio.to_thread(ensure_connected)
    start = time.time()

    # Parse intent + policy
    try:
        intent, policy = await asyncio.to_thread(parse_intent_with_policy, text)
    except Exception as e:
        return _error_response("PARSE_ERROR", f"Failed to parse intent: {e}", 400, "Format: 'send 10 USDC from Base to Arbitrum'")

    # Run safe verdict trace
    try:
        result = await asyncio.to_thread(agent.safe_verdict_trace, intent, policy)
    except Exception as e:
        return _error_response("VERDICT_ERROR", f"Verdict failed: {e}", 500, "Run 'doctor' to check MCP connectivity")

    duration = int((time.time() - start) * 1000)
    trace_step("analyze-intent", {"text": text}, {"verdict": result.verdict}, duration)

    # Serialize decision steps with MCP inspector fields
    _STEP_META = {
        "Parse Intent": {
            "purpose": "Extract structured intent from natural language",
            "why": "Natural language must be decomposed into chain IDs, token, and amount before any MCP call.",
        },
        "Parse Policy": {
            "purpose": "Extract policy constraints from natural language",
            "why": "Policy constraints (fee limits, chain avoidance) are parsed from free text to enforce programmatically.",
        },
        "Check Supported Route": {
            "purpose": "Verify route exists in LI.FI network",
            "why": "If no solver supports this chain pair, the transfer cannot proceed regardless of quote.",
        },
        "Check Route Health": {
            "purpose": "Verify solver availability for this route",
            "why": "A supported route may still be unhealthy if solvers are offline or liquidity is depleted.",
        },
        "Get Quote": {
            "purpose": "Request real-time solver quote from LI.FI network",
            "why": "The quote determines the actual output amount and fee, which policy constraints are evaluated against.",
        },
        "Calculate Fee": {
            "purpose": "Compute transfer fee percentage",
            "why": "Fee = (input - output) / input * 100. This derived value drives the fee policy check.",
        },
        "Fee Policy": {
            "purpose": "Enforce user-defined fee constraint",
            "why": "Compares calculated fee against the user's max_fee_pct limit to decide EXECUTABLE vs REFUSED.",
        },
        "Output Policy": {
            "purpose": "Enforce user-defined minimum output constraint",
            "why": "Ensures the solver's output meets the user's minimum acceptable amount.",
        },
        "Avoid Chains": {
            "purpose": "Enforce user-defined chain avoidance constraint",
            "why": "The user may want to avoid specific chains for regulatory, cost, or preference reasons.",
        },
        "Cross-Chain": {
            "purpose": "Enforce cross-chain transfer restriction",
            "why": "Some policies only allow same-chain transfers; this step validates that constraint.",
        },
    }

    steps = []
    for s in result.steps:
        meta = _STEP_META.get(s.name, {})
        # Build input_summary from mcp_args or step detail
        input_summary = ""
        if s.mcp_args:
            input_summary = ", ".join(f"{k}={v}" for k, v in s.mcp_args.items())
        elif s.name == "Parse Intent":
            input_summary = f'"{text}"'
        elif s.name == "Parse Policy":
            input_summary = f'"{text}"'
        elif s.name == "Calculate Fee":
            input_summary = f"input={intent.amount}, output={s.detail.split(':')[-1].strip().rstrip('%') if ':' in s.detail else '?'}"

        # Build output_summary from mcp_result or detail
        output_summary = ""
        if s.mcp_result:
            if s.mcp_tool == "get-supported-routes":
                route_count = len(s.mcp_result.get("data", {}).get("routes", []))
                output_summary = f"{route_count} routes found"
            elif s.mcp_tool == "request-quote":
                quotes = s.mcp_result.get("data", {}).get("quotes", [])
                if quotes:
                    q = quotes[0]
                    output_summary = f"output={q.get('outputAmount', '?')}, quoteId={q.get('quoteId', '?')[:16]}..."
                else:
                    output_summary = "No quotes returned"
            elif s.mcp_tool == "check-route-health":
                status = s.mcp_result.get("data", {}).get("status", "unknown")
                output_summary = f"status={status}"
        elif s.name == "Calculate Fee":
            output_summary = s.detail
        elif s.name in ("Fee Policy", "Output Policy", "Avoid Chains", "Cross-Chain"):
            output_summary = s.detail

        steps.append({
            "name": s.name,
            "status": s.status,
            "detail": s.detail,
            "duration_ms": s.duration_ms,
            "mcp_tool": s.mcp_tool,
            "purpose": meta.get("purpose", ""),
            "input_summary": input_summary,
            "output_summary": output_summary,
            "why": meta.get("why", ""),
        })

    return {
        "intent": {
            "amount": intent.amount,
            "token": intent.token.upper(),
            "from_chain": intent.from_chain,
            "to_chain": intent.to_chain,
        },
        "policy": {
            "max_fee_pct": policy.max_fee_pct,
            "min_output_amount": policy.min_output_amount,
            "require_healthy_route": policy.require_healthy_route,
            "allow_cross_chain": policy.allow_cross_chain,
            "avoid_chains": policy.avoid_chains,
        },
        "quote_params": {
            "fromChain": intent.from_chain_name(),
            "toChain": intent.to_chain_name(),
            "fromToken": intent.token_symbol(),
            "toToken": intent.token_symbol(),
            "amount": intent.amount,
        },
        "verdict": result.verdict,
        "reason": result.reason,
        "steps": steps,
        "total_duration_ms": result.total_duration_ms,
    }


# ── Judge Mode ──────────────────────────────────────────────────────

@app.get("/api/judge-mode")
async def judge_mode():
    """Run 5 key presets sequentially and compare expected vs actual verdict."""
    await asyncio.to_thread(ensure_connected)
    judge_presets = ["safe-transfer", "fee-too-high", "avoid-chain", "min-output", "doctor"]
    results = []

    for i, name in enumerate(judge_presets, 1):
        if name == "doctor":
            report = await asyncio.to_thread(agent.doctor)
            # Categorize failures
            critical_keywords = ["MCP endpoint unreachable", "Session", "protocol", "tools/list unavailable"]
            critical_failures = []
            warnings = []

            for g in report.get("groups", []):
                for c in g.get("checks", []):
                    if not c["passed"]:
                        detail = c.get("detail", "")
                        name_str = c.get("name", "")
                        is_critical = any(kw.lower() in detail.lower() or kw.lower() in name_str.lower()
                                          for kw in critical_keywords)
                        entry = f"{name_str}: {detail}"
                        if is_critical:
                            critical_failures.append(entry)
                        else:
                            warnings.append(entry)

            # Doctor-level warnings (non-check warnings)
            for w in report.get("warnings", []):
                warnings.append(f"{w.get('name', '')}: {w.get('detail', '')}")

            has_critical = len(critical_failures) > 0
            results.append({
                "step_num": i,
                "preset_name": "doctor",
                "description": "Run diagnostic checks on MCP connection",
                "expected_verdict": "PASS",
                "actual_verdict": "FAIL" if has_critical else "PASS",
                "match": not has_critical,
                "reason": f"Mode: {report.get('mode', '?')}, Endpoint: {report.get('endpoint', '?')}",
                "critical_failures": critical_failures,
                "warnings": warnings,
            })
            continue

        preset = PRESETS.get(name)
        if not preset:
            continue
        try:
            intent_data = preset["intent"]
            intent = Intent(intent_data["from_chain"], intent_data["to_chain"],
                            intent_data["token"], intent_data["amount"])
            field_names = {f.name for f in dataclasses.fields(Policy)}
            policy = Policy(**{k: v for k, v in preset["policy"].items() if k in field_names})
            result = await asyncio.to_thread(agent.safe_verdict_trace, intent, policy)
            actual = result.verdict
            expected = preset.get("expected_verdict", "EXECUTABLE")
            results.append({
                "step_num": i,
                "preset_name": name,
                "description": preset["description"],
                "expected_verdict": expected,
                "actual_verdict": actual,
                "match": expected == actual,
                "reason": result.reason,
            })
        except Exception as e:
            results.append({
                "step_num": i,
                "preset_name": name,
                "description": preset.get("description", ""),
                "expected_verdict": preset.get("expected_verdict", "EXECUTABLE"),
                "actual_verdict": "ERROR",
                "match": False,
                "reason": str(e),
            })

    return {"results": results}


# ── Preset Report ───────────────────────────────────────────────────

@app.get("/api/preset-report")
async def preset_report():
    """Run ALL 10 presets and compare expected vs actual verdict."""
    await asyncio.to_thread(ensure_connected)
    results = []

    for name, preset in PRESETS.items():
        try:
            intent_data = preset["intent"]
            intent = Intent(intent_data["from_chain"], intent_data["to_chain"],
                            intent_data["token"], intent_data["amount"])
            field_names = {f.name for f in dataclasses.fields(Policy)}
            policy = Policy(**{k: v for k, v in preset["policy"].items() if k in field_names})
            result = await asyncio.to_thread(agent.safe_verdict_trace, intent, policy)
            actual = result.verdict
            expected = preset.get("expected_verdict", "EXECUTABLE")
            results.append({
                "name": name,
                "expected": expected,
                "actual": actual,
                "match": expected == actual,
                "reason": result.reason,
            })
        except Exception as e:
            results.append({
                "name": name,
                "expected": preset.get("expected_verdict", "EXECUTABLE"),
                "actual": "ERROR",
                "match": False,
                "reason": str(e),
            })

    matched = sum(1 for r in results if r["match"])
    return {
        "results": results,
        "summary": {
            "total": len(results),
            "matched": matched,
            "mismatched": len(results) - matched,
        },
    }


# ── MCP Proof ───────────────────────────────────────────────────────

@app.get("/api/mcp-proof")
async def mcp_proof():
    """Prove the project uses real MCP connections by running a live quote."""
    await asyncio.to_thread(ensure_connected)
    start = time.time()
    try:
        intent = Intent("base", "arbitrum", "usdc", "1")
        result = await asyncio.to_thread(agent.get_quote, intent)
        quotes = result.get("data", {}).get("quotes", [])
        last_quote = None
        if quotes:
            q = quotes[0]
            fee_pct = agent._calc_fee("1", q.get("outputAmount", "0"), "usdc")
            last_quote = {
                "route": "Base → Arbitrum",
                "input": "1 USDC",
                "output": q.get("outputAmount", "?"),
                "fee_pct": fee_pct,
                "verdict": "EXECUTABLE",
                "timestamp": time.time(),
            }
        routes_result = await asyncio.to_thread(agent.get_routes)
        routes_count = len(routes_result.get("data", {}).get("routes", []))
    except Exception as e:
        last_quote = {"error": str(e), "timestamp": time.time()}
        routes_count = 0

    real_mcp = agent.mcp.mode in ("local_mcp", "strict")

    return {
        "mode": agent.mcp.mode,
        "real_mcp": real_mcp,
        "mcp_server": "LI.FI Intents MCP",
        "endpoint": agent.mcp.url,
        "routes_count": routes_count,
        "last_quote": last_quote,
    }


# ── Web UI ──────────────────────────────────────────────────────────

_INDEX_HTML: str | None = None

def _load_index_html() -> str:
    global _INDEX_HTML
    if _INDEX_HTML is None:
        tpl = Path(__file__).parent / "templates" / "index.html"
        _INDEX_HTML = tpl.read_text(encoding="utf-8")
    return _INDEX_HTML

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(_load_index_html())