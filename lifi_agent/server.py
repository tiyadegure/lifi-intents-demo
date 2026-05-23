"""LI.FI Intents Agent — Web API server."""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import asyncio
import collections
import html as html_mod
import json
import os
import threading
import time

from lifi_agent.agent import LifAgent, Intent, parse_intent, parse_intent_with_policy

app = FastAPI(title="LI.FI Intents Agent", version="1.0.0")
agent = LifAgent()

# ── Reasoning trace storage ─────────────────────────────────────────
traces = collections.deque(maxlen=200)
traces_lock = threading.Lock()
_connect_lock = threading.Lock()


def _escape_html(value: str) -> str:
    """Escape a string for safe insertion into HTML."""
    return html_mod.escape(str(value), quote=True)


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

@app.on_event("startup")
async def startup():
    # MCP connects lazily on first request
    pass


def ensure_connected():
    """Lazy MCP connection (skip in demo mode)."""
    if os.environ.get("LIFI_AGENT_DEMO_MODE") == "1":
        return
    if not agent.mcp._connected:
        with _connect_lock:
            if not agent.mcp._connected:
                try:
                    agent.connect()
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


@app.get("/api/quote")
async def get_quote(from_chain: str, to_chain: str, token: str, amount: str):
    # Input validation
    valid_chains = {"ethereum", "base", "arbitrum", "optimism", "polygon", "bsc", "avalanche", "zksync", "linea", "scroll", "blast", "mantle", "sonic"}
    valid_tokens = {"usdc", "usdt", "eth", "weth"}
    if from_chain.lower() not in valid_chains:
        return JSONResponse({"error": f"Invalid from_chain: {from_chain}"}, status_code=400)
    if to_chain.lower() not in valid_chains:
        return JSONResponse({"error": f"Invalid to_chain: {to_chain}"}, status_code=400)
    if token.lower() not in valid_tokens:
        return JSONResponse({"error": f"Invalid token: {token}"}, status_code=400)
    try:
        float(amount)
    except ValueError:
        return JSONResponse({"error": f"Invalid amount: {amount}"}, status_code=400)

    await asyncio.to_thread(ensure_connected)
    start = time.time()
    try:
        intent = await asyncio.to_thread(
            parse_intent, f"send {amount} {token} from {from_chain} to {to_chain}"
        )
        result = await asyncio.to_thread(agent.get_quote, intent)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
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
        return JSONResponse({"error": str(e)}, status_code=400)
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


@app.post("/api/explain")
async def explain_intent(request: Request):
    """Explain intent without executing — shows parsed intent, policy, and execution plan."""
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "No intent text provided"}, status_code=400)
    
    try:
        result = await asyncio.to_thread(agent.explain, text)
        return result
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/analyze-intent")
async def analyze_intent(request: Request):
    """Full Safe Verdict analysis: parse intent → policy → MCP calls → decision trace."""
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "No intent text provided"}, status_code=400)

    await asyncio.to_thread(ensure_connected)
    start = time.time()

    # Parse intent + policy
    try:
        intent, policy = await asyncio.to_thread(parse_intent_with_policy, text)
    except Exception as e:
        return JSONResponse({"error": f"Failed to parse intent: {e}"}, status_code=400)

    # Run safe verdict trace
    try:
        result = await asyncio.to_thread(agent.safe_verdict_trace, intent, policy)
    except Exception as e:
        return JSONResponse({"error": f"Verdict failed: {e}"}, status_code=500)

    duration = int((time.time() - start) * 1000)
    trace_step("analyze-intent", {"text": text}, {"verdict": result.verdict}, duration)

    # Serialize decision steps
    steps = []
    for s in result.steps:
        steps.append({
            "name": s.name,
            "status": s.status,
            "detail": s.detail,
            "duration_ms": s.duration_ms,
            "mcp_tool": s.mcp_tool,
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