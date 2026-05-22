"""LI.FI Intents Agent — Web API server."""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import asyncio
import collections
import html as html_mod
import json
import threading
import time

from lifi_agent.agent import LifAgent, Intent, parse_intent

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
    """Lazy MCP connection."""
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
        try:
            t0 = time.time()
            health = agent.check_route_health(from_id, to_id)
            elapsed = int((time.time() - t0) * 1000)
            total_response_ms += elapsed
            checked += 1
            is_healthy = health.get("data", {}).get("healthy", True)
            if is_healthy:
                total_routes += 1
            from_name = r.get("fromChain", {}).get("name", from_id)
            to_name = r.get("toChain", {}).get("name", to_id)
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


# ── Web UI ──────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LI.FI Intents × AI Agent</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  *{margin:0;padding:0;box-sizing:border-box}
  :root{
    --bg-base:#060a13;--bg-surface:#0c1220;--bg-card:#111a2e;--bg-card-hover:#162040;
    --border:#1e2d4a;--border-subtle:#162040;
    --text-primary:#e8edf5;--text-secondary:#8494b2;--text-muted:#4a5a7a;
    --accent:#6c5ce7;--accent-glow:#6c5ce733;
    --green:#00d68f;--green-dim:#00d68f22;
    --red:#ff6b6b;--red-dim:#ff6b6b22;
    --amber:#ffa94d;--amber-dim:#ffa94d22;
    --radius:12px;--radius-sm:8px;
  }
  body{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:var(--bg-base);color:var(--text-primary);min-height:100vh;-webkit-font-smoothing:antialiased}
  .container{max-width:1040px;margin:0 auto;padding:24px 20px}
  /* Header */
  header{text-align:center;padding:40px 0 28px;position:relative}
  header::after{content:'';position:absolute;bottom:0;left:50%;transform:translateX(-50%);width:200px;height:1px;background:linear-gradient(90deg,transparent,var(--accent),transparent)}
  header h1{font-size:32px;font-weight:700;background:linear-gradient(135deg,#a78bfa,#6c5ce7,#4f8cff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;letter-spacing:-0.5px}
  header p{color:var(--text-secondary);margin-top:10px;font-size:14px;font-weight:400;letter-spacing:0.2px}
  /* Input row */
  .input-row{display:flex;gap:10px;margin:28px 0 20px;align-items:stretch}
  .input-row input{flex:1;min-width:0;background:var(--bg-surface);border:1px solid var(--border);color:var(--text-primary);padding:12px 16px;border-radius:var(--radius-sm);font-size:14px;font-family:inherit;outline:none;transition:border-color .2s,box-shadow .2s}
  .input-row input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow)}
  .input-row input::placeholder{color:var(--text-muted)}
  .btn{background:linear-gradient(135deg,#6c5ce7,#5a4bd1);color:#fff;border:none;padding:12px 24px;border-radius:var(--radius-sm);cursor:pointer;font-size:14px;font-weight:600;font-family:inherit;transition:transform .1s,box-shadow .2s,opacity .2s;white-space:nowrap}
  .btn:hover{box-shadow:0 4px 20px var(--accent-glow);transform:translateY(-1px)}
  .btn:active{transform:translateY(0)}
  .btn:disabled{opacity:.45;cursor:not-allowed;transform:none;box-shadow:none}
  .btn-secondary{background:var(--bg-surface);border:1px solid var(--border);color:var(--text-secondary)}
  .btn-secondary:hover{border-color:var(--accent);color:var(--text-primary);box-shadow:0 0 0 3px var(--accent-glow)}
  /* Status */
  #status{min-height:24px;margin-bottom:8px}
  .status{padding:10px 16px;border-radius:var(--radius-sm);font-size:13px;font-weight:500;display:flex;align-items:center;gap:10px;animation:fadeSlideIn .3s ease}
  .status.ok{background:var(--green-dim);color:var(--green);border:1px solid #00d68f33}
  .status.err{background:var(--red-dim);color:var(--red);border:1px solid #ff6b6b33}
  /* Grid */
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
  /* Panel */
  .panel{background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius);padding:24px;transition:border-color .2s}
  .panel:hover{border-color:#2a3f6a}
  .panel h3{color:var(--text-primary);font-size:15px;font-weight:600;margin-bottom:18px;display:flex;align-items:center;gap:10px;letter-spacing:-0.2px}
  .panel h3 .badge{background:linear-gradient(135deg,#6c5ce7,#5a4bd1);color:#fff;font-size:10px;padding:3px 10px;border-radius:20px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px}
  .panel h3 .badge-live{background:linear-gradient(135deg,#00d68f,#00b87a);color:#013d28}
  /* Quote cards with gradient border */
  .quote-card{position:relative;border-radius:var(--radius-sm);padding:1px;margin-bottom:12px;background:linear-gradient(135deg,#2a3f6a,#1e2d4a,#2a3f6a);animation:fadeSlideIn .35s ease both}
  .quote-card:nth-child(2){animation-delay:.08s}
  .quote-card:nth-child(3){animation-delay:.16s}
  .quote-card-inner{background:var(--bg-card);border-radius:calc(var(--radius-sm) - 1px);padding:16px 18px;transition:background .2s}
  .quote-card:hover .quote-card-inner{background:var(--bg-card-hover)}
  .quote-card .label{color:var(--text-muted);font-size:11px;text-transform:uppercase;letter-spacing:1px;font-weight:600}
  .quote-card .value{font-size:26px;font-weight:700;color:var(--green);margin:6px 0 2px;font-variant-numeric:tabular-nums}
  .quote-card .value-dim{color:var(--text-primary)}
  .quote-card .meta{color:var(--text-secondary);font-size:13px}
  /* Highlight card */
  .quote-card-highlight{background:linear-gradient(135deg,#6c5ce740,#4f8cff30,#6c5ce740)}
  .quote-card-highlight .quote-card-inner{background:linear-gradient(135deg,#111a2e,#151f38)}
  /* Traces */
  .trace-item{display:flex;gap:12px;padding:10px 0;border-bottom:1px solid var(--border-subtle);font-size:13px;animation:fadeSlideIn .25s ease both}
  .trace-item:last-child{border-bottom:none}
  .trace-tool{color:var(--amber);font-weight:600;min-width:150px;font-size:12px;font-family:'SF Mono',SFMono-Regular,Consolas,monospace}
  .trace-duration{color:var(--text-muted);min-width:55px;text-align:right;font-variant-numeric:tabular-nums;font-size:12px}
  .trace-result{color:var(--green);flex:1;word-break:break-word}
  .trace-error{color:var(--red)}
  /* Compare table */
  .compare-table{width:100%;border-collapse:separate;border-spacing:0}
  .compare-table th{text-align:left;color:var(--text-muted);font-size:11px;padding:10px 12px;border-bottom:1px solid var(--border);text-transform:uppercase;letter-spacing:0.8px;font-weight:600}
  .compare-table td{padding:12px;font-size:14px;border-bottom:1px solid var(--border-subtle);transition:background .15s}
  .compare-table tbody tr:hover td{background:var(--bg-card)}
  .compare-table tbody tr:first-child td{color:var(--green);font-weight:600}
  .compare-table tbody tr:first-child td:first-child::before{content:'';display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--green);margin-right:8px;vertical-align:middle}
  .compare-fee{font-variant-numeric:tabular-nums}
  .compare-table tbody tr.winner td{background:var(--green-dim);border-left:2px solid var(--green)}
  /* Copy button */
  .copy-btn{background:none;border:1px solid var(--border);color:var(--text-muted);cursor:pointer;padding:2px 8px;border-radius:4px;font-size:11px;margin-left:8px;transition:all .15s;font-family:inherit}
  .copy-btn:hover{border-color:var(--accent);color:var(--text-primary)}
  .copy-btn.copied{border-color:var(--green);color:var(--green)}
  /* Trace dedup badge */
  .trace-count{background:var(--red-dim);color:var(--red);font-size:10px;padding:1px 6px;border-radius:10px;margin-left:6px;font-weight:600}
  /* How it works */
  .how-it-works{margin-top:20px;padding:20px 24px;text-align:center}
  .how-it-works h3{color:var(--text-secondary);font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:1px;margin-bottom:14px}
  .flow-steps{display:flex;align-items:center;justify-content:center;gap:8px;flex-wrap:wrap;font-size:13px;color:var(--text-secondary)}
  .flow-step{display:flex;align-items:center;gap:5px;background:var(--bg-card);padding:6px 12px;border-radius:6px;border:1px solid var(--border-subtle)}
  .flow-step .icon{font-size:15px}
  .flow-arrow{color:var(--text-muted);font-size:14px}
  /* Loading spinner */
  .loading{display:inline-block;width:14px;height:14px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite;vertical-align:middle}
  @keyframes spin{to{transform:rotate(360deg)}}
  @keyframes fadeSlideIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
  @keyframes pulse{0%,100%{opacity:.4}50%{opacity:.8}}
  /* Skeleton loading */
  .skeleton{background:linear-gradient(90deg,var(--bg-card) 25%,var(--bg-card-hover) 50%,var(--bg-card) 75%);background-size:200% 100%;animation:pulse 1.5s ease-in-out infinite;border-radius:6px;height:16px;margin:8px 0}
  .skeleton.w60{width:60%}.skeleton.w40{width:40%}.skeleton.w80{width:80%}
  /* Empty state */
  .empty-state{color:var(--text-muted);font-size:13px;padding:8px 0}
  /* Footer */
  .footer{text-align:center;padding:28px 0 12px;color:var(--text-muted);font-size:12px;border-top:1px solid var(--border-subtle);margin-top:28px}
  .footer a{color:var(--accent);text-decoration:none;transition:color .15s}
  .footer a:hover{color:#a78bfa}
  /* Stats bar */
  .stats-bar{display:flex;align-items:center;justify-content:center;gap:24px;padding:10px 20px;background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:20px;font-size:12px;color:var(--text-secondary)}
  .stats-bar .stat{display:flex;align-items:center;gap:6px}
  .stats-bar .stat-value{color:var(--text-primary);font-weight:600;font-variant-numeric:tabular-nums}
  .stats-bar .stat-dot{width:6px;height:6px;border-radius:50%;background:var(--green);flex-shrink:0}
  /* Solver grid */
  .solver-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:14px}
  .solver-card{background:var(--bg-card);border:1px solid var(--border-subtle);border-radius:var(--radius-sm);padding:14px 16px;transition:border-color .2s,background .2s;animation:fadeSlideIn .3s ease both}
  .solver-card:hover{border-color:#2a3f6a;background:var(--bg-card-hover)}
  .solver-card-header{display:flex;align-items:center;gap:8px;margin-bottom:10px}
  .solver-card-header .solver-status{width:8px;height:8px;border-radius:50%;background:var(--green);flex-shrink:0;box-shadow:0 0 6px var(--green-dim)}
  .solver-card-header .solver-name{font-size:13px;font-weight:600;color:var(--text-primary);font-family:'SF Mono',SFMono-Regular,Consolas,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .solver-chains{display:flex;flex-wrap:wrap;gap:4px}
  .solver-chain-badge{background:var(--bg-surface);border:1px solid var(--border-subtle);color:var(--text-secondary);font-size:10px;padding:2px 8px;border-radius:10px;font-weight:500;text-transform:capitalize}
  /* Solver Analytics */
  .analytics-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}
  .analytics-card{background:var(--bg-card);border:1px solid var(--border-subtle);border-radius:var(--radius-sm);padding:18px 16px;text-align:center;transition:border-color .2s,background .2s;animation:fadeSlideIn .3s ease both}
  .analytics-card:hover{border-color:#2a3f6a;background:var(--bg-card-hover)}
  .analytics-card .analytics-icon{font-size:22px;margin-bottom:8px;display:block}
  .analytics-card .analytics-value{font-size:28px;font-weight:700;color:var(--text-primary);font-variant-numeric:tabular-nums;line-height:1.2}
  .analytics-card .analytics-value.green{color:var(--green)}
  .analytics-card .analytics-label{font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.8px;font-weight:600;margin-top:6px}
  .analytics-card .analytics-unit{font-size:12px;color:var(--text-secondary);font-weight:400}
  /* Chain distribution bar chart */
  .chain-bar-chart{margin-top:4px}
  .chain-bar-row{display:flex;align-items:center;gap:10px;margin-bottom:10px;animation:fadeSlideIn .3s ease both}
  .chain-bar-label{font-size:12px;color:var(--text-secondary);min-width:80px;text-align:right;font-weight:500;text-transform:capitalize}
  .chain-bar-track{flex:1;height:22px;background:var(--bg-card);border-radius:4px;overflow:hidden;border:1px solid var(--border-subtle);position:relative}
  .chain-bar-fill{height:100%;border-radius:3px;background:linear-gradient(90deg,var(--accent),#4f8cff);transition:width .6s ease;display:flex;align-items:center;justify-content:flex-end;padding-right:8px}
  .chain-bar-count{font-size:10px;color:#fff;font-weight:700;text-shadow:0 1px 2px rgba(0,0,0,.4)}
  .analytics-section-title{font-size:13px;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.8px;margin-bottom:14px}
  /* Mobile */
  @media(max-width:768px){
    .container{padding:16px 14px}
    header{padding:24px 0 20px}
    header h1{font-size:24px}
    .input-row{flex-direction:column;gap:8px}
    .input-row .btn-row{display:flex;gap:8px}
    .btn{padding:12px 16px}
    .grid{grid-template-columns:1fr;gap:16px}
    .panel{padding:18px 14px}
    .quote-card .value{font-size:22px}
    .trace-item{flex-wrap:wrap;gap:6px}
    .trace-tool{min-width:auto;font-size:11px}
    .trace-duration{min-width:auto}
    .compare-table{font-size:13px}
    .compare-table th,.compare-table td{padding:8px 10px}
    .solver-grid{grid-template-columns:1fr}
    .stats-bar{flex-wrap:wrap;gap:12px;padding:8px 14px;font-size:11px}
    .analytics-grid{grid-template-columns:repeat(2,1fr);gap:10px}
    .analytics-card .analytics-value{font-size:22px}
  }
  @media(max-width:420px){
    header h1{font-size:20px}
    header p{font-size:12px}
  }
  /* Solver Tools */
  .solver-tool-section{margin-bottom:0}
  .solver-tool-title{font-size:15px;font-weight:600;color:var(--text-primary);margin-bottom:4px}
  .solver-tool-desc{font-size:13px;color:var(--text-secondary);margin-bottom:14px}
  .solver-tool-controls{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;margin-bottom:14px}
  .solver-tool-field{display:flex;flex-direction:column;gap:4px}
  .solver-tool-field label{font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;font-weight:600}
  .solver-tool-field select{background:var(--bg-base);border:1px solid var(--border);color:var(--text-primary);padding:8px 12px;border-radius:var(--radius-sm);font-size:13px;font-family:inherit;outline:none;cursor:pointer;min-width:140px;transition:border-color .2s}
  .solver-tool-field select:focus{border-color:var(--accent)}
  .solver-tool-divider{height:1px;background:var(--border-subtle);margin:20px 0}
  .health-card{background:var(--bg-card);border:1px solid var(--border-subtle);border-radius:var(--radius-sm);padding:16px 18px;margin-top:10px;animation:fadeSlideIn .3s ease both}
  .health-card.healthy{border-left:3px solid var(--green)}
  .health-card.unhealthy{border-left:3px solid var(--red)}
  .health-card.unknown{border-left:3px solid var(--amber)}
  .health-status{display:flex;align-items:center;gap:8px;margin-bottom:8px}
  .health-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
  .health-dot.green{background:var(--green);box-shadow:0 0 6px var(--green-dim)}
  .health-dot.red{background:var(--red);box-shadow:0 0 6px var(--red-dim)}
  .health-dot.amber{background:var(--amber);box-shadow:0 0 6px var(--amber-dim)}
  .health-label{font-size:14px;font-weight:600;color:var(--text-primary)}
  .health-meta{font-size:13px;color:var(--text-secondary)}
  .health-meta code{background:var(--bg-surface);padding:1px 6px;border-radius:4px;font-size:12px;color:var(--text-primary)}
  .inventory-card{background:var(--bg-card);border:1px solid var(--border-subtle);border-radius:var(--radius-sm);padding:14px 16px;margin-top:10px;animation:fadeSlideIn .3s ease both}
  .inventory-card:hover{border-color:#2a3f6a;background:var(--bg-card-hover)}
  .inventory-row{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border-subtle);font-size:13px}
  .inventory-row:last-child{border-bottom:none}
  .inventory-key{color:var(--text-muted);font-weight:500}
  .inventory-val{color:var(--text-primary);font-weight:600;font-variant-numeric:tabular-nums}
  /* Become a Solver */
  .solver-guide-intro{color:var(--text-secondary);font-size:14px;line-height:1.6;margin-bottom:20px}
  .solver-steps{display:flex;flex-direction:column;gap:16px;margin-bottom:24px}
  .solver-step{display:flex;gap:14px;background:var(--bg-card);border:1px solid var(--border-subtle);border-radius:var(--radius-sm);padding:18px 20px;transition:border-color .2s,background .2s}
  .solver-step:hover{border-color:#2a3f6a;background:var(--bg-card-hover)}
  .solver-step-num{width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,#6c5ce7,#5a4bd1);color:#fff;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;flex-shrink:0}
  .solver-step-body{flex:1}
  .solver-step-title{font-size:14px;font-weight:600;color:var(--text-primary);margin-bottom:4px}
  .solver-step-desc{font-size:13px;color:var(--text-secondary);line-height:1.5}
  .solver-code-block{margin-top:12px;background:var(--bg-base);border:1px solid var(--border);border-radius:var(--radius-sm);overflow:hidden}
  .solver-code-header{display:flex;justify-content:space-between;align-items:center;padding:8px 14px;background:var(--bg-surface);border-bottom:1px solid var(--border-subtle);font-size:12px;color:var(--text-muted);font-weight:600}
  .solver-code-lang{background:var(--accent-glow);color:var(--accent);padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600}
  .solver-code{padding:14px 16px;margin:0;font-size:12px;line-height:1.6;overflow-x:auto;color:var(--text-secondary);font-family:'SF Mono',SFMono-Regular,Consolas,monospace}
  .solver-code code{color:inherit}
  .solver-links{margin-top:4px}
  .solver-links-title{font-size:13px;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.8px;margin-bottom:12px}
  .solver-link-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
  .solver-link-card{display:flex;flex-direction:column;gap:4px;background:var(--bg-card);border:1px solid var(--border-subtle);border-radius:var(--radius-sm);padding:14px 16px;text-decoration:none;transition:border-color .2s,background .2s}
  .solver-link-card:hover{border-color:var(--accent);background:var(--bg-card-hover)}
  .solver-link-icon{font-size:18px}
  .solver-link-label{font-size:13px;font-weight:600;color:var(--text-primary)}
  .solver-link-desc{font-size:12px;color:var(--text-muted);line-height:1.4}
  @media(max-width:768px){
    .solver-tool-controls{flex-direction:column;align-items:stretch}
    .solver-tool-field select{min-width:auto}
    .solver-link-grid{grid-template-columns:1fr}
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>LI.FI Intents × AI Agent</h1>
    <p>Cross-chain operations via natural language · Powered by MCP Protocol</p>
  </header>

  <div class="stats-bar" id="statsBar">
    <div class="stat"><span class="stat-dot"></span> Routes: <span class="stat-value" id="statRoutes">—</span></div>
    <div class="stat"><span class="stat-dot"></span> Active Solvers: <span class="stat-value" id="statSolvers">—</span></div>
    <div class="stat">Last Quote: <span class="stat-value" id="statLastQuote">—</span></div>
  </div>

  <div class="input-row">
    <input type="text" id="intentInput" placeholder="send 10 USDC from Base to Arbitrum" spellcheck="false" autocomplete="off" />
    <button class="btn" id="submitBtn" onclick="submitIntent()">Get Quote</button>
    <button class="btn btn-secondary" onclick="compareQuotes()">Compare</button>
  </div>

  <div id="status"></div>

  <div class="grid">
    <div class="panel">
      <h3>Quote Result <span class="badge badge-live" id="quoteBadge" style="display:none">LIVE</span></h3>
      <div id="quoteResult">
        <p class="empty-state">Enter an intent to get a cross-chain quote from the solver network.</p>
      </div>
    </div>

    <div class="panel">
      <h3>Agent Reasoning <span class="badge" id="traceBadge">0 steps</span></h3>
      <div id="traces">
        <p class="empty-state">Agent tool calls will appear here in real-time.</p>
      </div>
    </div>
  </div>

  <div class="panel" style="margin-top:20px">
    <h3>Route Comparison</h3>
    <div id="compareResult">
      <p class="empty-state">Click "Compare" to see quotes across multiple destination chains.</p>
    </div>
  </div>

  <div class="panel" style="margin-top:20px">
    <h3>Solver Network <span class="badge" id="solverBadge">0 solvers</span></h3>
    <div id="solverResult">
      <p class="empty-state">Loading solver identities…</p>
    </div>
    <button class="btn btn-secondary" style="margin-top:14px" onclick="refreshSolvers()">Refresh Solvers</button>
  </div>

  <div class="panel" style="margin-top:20px">
    <h3>Solver Analytics <span class="badge" id="analyticsBadge">—</span></h3>
    <div id="analyticsResult">
      <div class="analytics-grid">
        <div class="analytics-card" style="animation-delay:0s">
          <span class="analytics-icon">📊</span>
          <div class="analytics-value" id="anTotal">—</div>
          <div class="analytics-label">Total Solvers</div>
        </div>
        <div class="analytics-card" style="animation-delay:.06s">
          <span class="analytics-icon">✅</span>
          <div class="analytics-value green" id="anActive">—</div>
          <div class="analytics-label">Active Solvers</div>
        </div>
        <div class="analytics-card" style="animation-delay:.12s">
          <span class="analytics-icon">🔗</span>
          <div class="analytics-value" id="anRoutes">—</div>
          <div class="analytics-label">Routes Covered</div>
        </div>
        <div class="analytics-card" style="animation-delay:.18s">
          <span class="analytics-icon">⚡</span>
          <div class="analytics-value" id="anAvgTime">—</div>
          <div class="analytics-label">Avg Response <span class="analytics-unit">(ms)</span></div>
        </div>
      </div>
      <div class="analytics-section-title">Solver Distribution by Chain</div>
      <div id="chainBarChart" class="chain-bar-chart">
        <p class="empty-state">Click "Refresh Stats" to load analytics.</p>
      </div>
    </div>
    <button class="btn btn-secondary" style="margin-top:14px" onclick="refreshSolverStats()">Refresh Stats</button>
  </div>

  <div class="panel how-it-works">
    <h3>How It Works</h3>
    <div class="flow-steps">
      <span class="flow-step"><span class="icon">💬</span> User Input</span>
      <span class="flow-arrow">→</span>
      <span class="flow-step"><span class="icon">🤖</span> AI Agent</span>
      <span class="flow-arrow">→</span>
      <span class="flow-step"><span class="icon">🔌</span> MCP Server</span>
      <span class="flow-arrow">→</span>
      <span class="flow-step"><span class="icon">🔗</span> LI.FI Intents</span>
      <span class="flow-arrow">→</span>
      <span class="flow-step"><span class="icon">⛓️</span> Cross-chain</span>
    </div>
  </div>

  <!-- Transaction Tracker -->
  <div class="panel">
    <h3>Transaction Tracker <span class="badge" id="trackerBadge">—</span></h3>
    <div style="display:flex;gap:10px;margin-bottom:16px">
      <input type="text" id="orderIdInput" placeholder="Enter Order ID..." style="flex:1;padding:10px 14px;background:var(--bg-base);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text-primary);font-family:inherit;font-size:14px">
      <button class="btn btn-primary" onclick="trackOrder()">Track</button>
    </div>
    <div id="trackerResult">
      <p class="empty-state">Enter an order ID to track its status.</p>
    </div>
    <div id="recentOrders" style="margin-top:16px">
      <div class="analytics-section-title">Recent Orders</div>
      <p class="empty-state">Loading recent orders...</p>
    </div>
  </div>

  <!-- Quote Statistics -->
  <div class="panel">
    <h3>📊 Quote Statistics <span class="badge" id="statsBadge">—</span></h3>
    <div id="statsResult" class="analytics-grid">
      <div class="analytics-card" style="animation-delay:0s">
        <span class="analytics-icon">📈</span>
        <div class="analytics-value" id="statTotal">—</div>
        <div class="analytics-label">Total Quotes</div>
      </div>
      <div class="analytics-card" style="animation-delay:.06s">
        <span class="analytics-icon">💰</span>
        <div class="analytics-value" id="statAvgFee">—</div>
        <div class="analytics-label">Avg Fee</div>
      </div>
      <div class="analytics-card" style="animation-delay:.12s">
        <span class="analytics-icon">🏆</span>
        <div class="analytics-value" id="statTopRoute">—</div>
        <div class="analytics-label">Top Route</div>
      </div>
      <div class="analytics-card" style="animation-delay:.18s">
        <span class="analytics-icon">🪙</span>
        <div class="analytics-value" id="statTopToken">—</div>
        <div class="analytics-label">Top Token</div>
      </div>
    </div>
  </div>

  <!-- Solver Tools -->
  <div class="panel" style="margin-top:20px">
    <h3>🛠️ Solver Tools <span class="badge">MCP</span></h3>

    <!-- Route Health Checker -->
    <div class="solver-tool-section">
      <div class="solver-tool-title">Route Health Checker</div>
      <div class="solver-tool-desc">Check if a route between two chains is healthy and available.</div>
      <div class="solver-tool-controls">
        <div class="solver-tool-field">
          <label>From Chain</label>
          <select id="healthFromChain">
            <option value="1">Ethereum</option>
            <option value="8453">Base</option>
            <option value="42161">Arbitrum</option>
            <option value="10">Optimism</option>
            <option value="137">Polygon</option>
            <option value="56">BSC</option>
            <option value="43114">Avalanche</option>
            <option value="324">zkSync</option>
            <option value="59144">Linea</option>
            <option value="534352">Scroll</option>
            <option value="81457">Blast</option>
            <option value="5000">Mantle</option>
            <option value="146">Sonic</option>
          </select>
        </div>
        <div class="solver-tool-field">
          <label>To Chain</label>
          <select id="healthToChain">
            <option value="42161">Arbitrum</option>
            <option value="1">Ethereum</option>
            <option value="8453">Base</option>
            <option value="10">Optimism</option>
            <option value="137">Polygon</option>
            <option value="56">BSC</option>
            <option value="43114">Avalanche</option>
            <option value="324">zkSync</option>
            <option value="59144">Linea</option>
            <option value="534352">Scroll</option>
            <option value="81457">Blast</option>
            <option value="5000">Mantle</option>
            <option value="146">Sonic</option>
          </select>
        </div>
        <button class="btn" onclick="checkRouteHealth()">Check Health</button>
      </div>
      <div id="healthResult"></div>
    </div>

    <div class="solver-tool-divider"></div>

    <!-- Quote Inventory Viewer -->
    <div class="solver-tool-section">
      <div class="solver-tool-title">Quote Inventory Viewer</div>
      <div class="solver-tool-desc">View standing quotes from solvers for a specific route and token pair.</div>
      <div class="solver-tool-controls">
        <div class="solver-tool-field">
          <label>From Chain</label>
          <select id="invFromChain">
            <option value="1">Ethereum</option>
            <option value="8453">Base</option>
            <option value="42161">Arbitrum</option>
            <option value="10">Optimism</option>
            <option value="137">Polygon</option>
            <option value="56">BSC</option>
            <option value="43114">Avalanche</option>
          </select>
        </div>
        <div class="solver-tool-field">
          <label>To Chain</label>
          <select id="invToChain">
            <option value="42161">Arbitrum</option>
            <option value="1">Ethereum</option>
            <option value="8453">Base</option>
            <option value="10">Optimism</option>
            <option value="137">Polygon</option>
            <option value="56">BSC</option>
            <option value="43114">Avalanche</option>
          </select>
        </div>
        <div class="solver-tool-field">
          <label>From Token</label>
          <select id="invFromToken">
            <option value="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48">USDC (ETH)</option>
            <option value="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913">USDC (Base)</option>
            <option value="0xaf88d065e77c8cC2239327C5EDb3A432268e5831">USDC (Arb)</option>
            <option value="0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85">USDC (OP)</option>
            <option value="0xdAC17F958D2ee523a2206206994597C13D831ec7">USDT (ETH)</option>
            <option value="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2">WETH (ETH)</option>
          </select>
        </div>
        <div class="solver-tool-field">
          <label>To Token</label>
          <select id="invToToken">
            <option value="0xaf88d065e77c8cC2239327C5EDb3A432268e5831">USDC (Arb)</option>
            <option value="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48">USDC (ETH)</option>
            <option value="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913">USDC (Base)</option>
            <option value="0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85">USDC (OP)</option>
            <option value="0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9">USDT (Arb)</option>
            <option value="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1">WETH (Arb)</option>
          </select>
        </div>
        <button class="btn" onclick="viewInventory()">View Inventory</button>
      </div>
      <div id="inventoryResult"></div>
    </div>
  </div>

  <!-- Become a Solver -->
  <div class="panel" style="margin-top:20px">
    <h3>🚀 Become a Solver</h3>
    <div class="solver-guide">
      <p class="solver-guide-intro">Solvers compete to fill cross-chain intents, earning fees on every transfer. Join the LI.FI solver network to provide liquidity and earn yield across chains.</p>

      <div class="solver-steps">
        <div class="solver-step">
          <div class="solver-step-num">1</div>
          <div class="solver-step-body">
            <div class="solver-step-title">Set Up Your Solver Infrastructure</div>
            <div class="solver-step-desc">Deploy solver nodes on the chains you want to support. You need liquidity pools and a relayer to fulfill intents. Minimum requirements: EVM-compatible node, funded wallet, and a reliable RPC endpoint per chain.</div>
          </div>
        </div>
        <div class="solver-step">
          <div class="solver-step-num">2</div>
          <div class="solver-step-body">
            <div class="solver-step-title">Register as a Solver</div>
            <div class="solver-step-desc">Submit your solver identity to the LI.FI Intents network. This includes your wallet address, supported chains, and the tokens you can provide quotes for.</div>
            <div class="solver-code-block">
              <div class="solver-code-header">Register via MCP <span class="solver-code-lang">TypeScript</span></div>
              <pre class="solver-code"><code>// Submit solver identity via LI.FI Intents API
const registration = await mcp.call("submit-standing-quotes", {
  quotes: [
    {
      fromChain: "1",         // Ethereum
      toChain: "42161",       // Arbitrum
      fromAsset: "0xA0b8...", // USDC on Ethereum
      toAsset: "0xaf88...",   // USDC on Arbitrum
      margin: "0.001",        // 0.1% fee
      minAmount: "1000000",   // 1 USDC (6 decimals)
      maxAmount: "10000000000" // 10,000 USDC
    }
  ]
});</code></pre>
            </div>
          </div>
        </div>
        <div class="solver-step">
          <div class="solver-step-num">3</div>
          <div class="solver-step-body">
            <div class="solver-step-title">Monitor and Optimize</div>
            <div class="solver-step-desc">Use the Route Health Checker and Quote Inventory tools above to monitor solver performance. Adjust margins based on competition and gas costs. Track your orders with the Transaction Tracker.</div>
          </div>
        </div>
        <div class="solver-step">
          <div class="solver-step-num">4</div>
          <div class="solver-step-body">
            <div class="solver-step-title">Scale Across Chains</div>
            <div class="solver-step-desc">Expand your solver to additional chains and token pairs. Solvers covering more routes earn more volume. Use the Solver Analytics above to identify high-demand, low-coverage routes.</div>
          </div>
        </div>
      </div>

      <div class="solver-links">
        <div class="solver-links-title">Resources</div>
        <div class="solver-link-grid">
          <a href="https://docs.li.fi/lifi-intents/solvers/overview" class="solver-link-card" target="_blank" rel="noopener">
            <span class="solver-link-icon">📖</span>
            <span class="solver-link-label">Solver Overview</span>
            <span class="solver-link-desc">Introduction to the LI.FI solver network</span>
          </a>
          <a href="https://docs.li.fi/lifi-intents/solvers/getting-started" class="solver-link-card" target="_blank" rel="noopener">
            <span class="solver-link-icon">⚡</span>
            <span class="solver-link-label">Getting Started</span>
            <span class="solver-link-desc">Step-by-step solver setup guide</span>
          </a>
          <a href="https://docs.li.fi/lifi-intents/api-reference" class="solver-link-card" target="_blank" rel="noopener">
            <span class="solver-link-icon">🔌</span>
            <span class="solver-link-label">API Reference</span>
            <span class="solver-link-desc">Full API docs for solver operations</span>
          </a>
          <a href="https://github.com/tiyadegure/lifi-intents-demo" class="solver-link-card" target="_blank" rel="noopener">
            <span class="solver-link-icon">💻</span>
            <span class="solver-link-label">Demo Source</span>
            <span class="solver-link-desc">Reference implementation on GitHub</span>
          </a>
        </div>
      </div>
    </div>
  </div>

  <div class="footer">
    <p>Built for LI.FI Intents Builder Challenge · <a href="https://docs.li.fi/lifi-intents/introduction">Docs</a> · <a href="https://github.com/tiyadegure/lifi-intents-demo">GitHub</a></p>
  </div>
</div>

<script>
function escapeHtml(s) {
  const d = document.createElement('div');
  d.appendChild(document.createTextNode(s == null ? '' : String(s)));
  return d.innerHTML;
}
const chains = ['ethereum','base','arbitrum','optimism','polygon','bsc'];
const tokens = ['USDC','USDT','ETH'];

function capitalize(s){return s.charAt(0).toUpperCase()+s.slice(1)}

function parseIntent(text) {
  text = text.toLowerCase().trim();
  const amountMatch = text.match(/(\\d+\\.?\\d*)\\s*(usdc|usdt|eth)/);
  if (!amountMatch) return null;
  const chainNames = chains.filter(c => text.includes(c));
  const fromMatch = text.match(/from\\s+(\\w+)/);
  const toMatch = text.match(/to\\s+(\\w+)/);
  return {
    amount: amountMatch[1],
    token: amountMatch[2].toUpperCase(),
    from: fromMatch && chains.includes(fromMatch[1]) ? fromMatch[1] : chainNames[0] || '',
    to: toMatch && chains.includes(toMatch[1]) ? toMatch[1] : chainNames[1] || ''
  };
}

function setStatus(msg, type) {
  document.getElementById('status').innerHTML = msg ? '<div class="status ' + type + '">' + msg + '</div>' : '';
}

function showSkeleton(id) {
  document.getElementById(id).innerHTML =
    '<div class="skeleton w60"></div><div class="skeleton w80"></div><div class="skeleton w40"></div>';
}

async function submitIntent() {
  const text = document.getElementById('intentInput').value;
  const intent = parseIntent(text);
  if (!intent) { setStatus('Could not parse intent. Try: send 10 USDC from Base to Arbitrum', 'err'); return; }
  if (!intent.from || !intent.to) { setStatus('Need two chains. Supported: ' + chains.join(', '), 'err'); return; }

  document.getElementById('submitBtn').disabled = true;
  setStatus('<span class="loading"></span> Querying solver network…', 'ok');
  showSkeleton('quoteResult');
  document.getElementById('quoteBadge').style.display = 'none';

  try {
    const url = '/api/quote?from_chain=' + intent.from + '&to_chain=' + intent.to + '&token=' + intent.token + '&amount=' + intent.amount;
    const res = await fetch(url);
    const data = await res.json();
    renderQuote(data, intent);
    refreshTraces();
    document.getElementById('statLastQuote').textContent = new Date().toLocaleTimeString();
  } catch (e) {
    setStatus('Request failed: ' + escapeHtml(e.message), 'err');
  }
  document.getElementById('submitBtn').disabled = false;
}

function renderQuote(data, intent) {
  const el = document.getElementById('quoteResult');
  const badge = document.getElementById('quoteBadge');
  if (data.error) {
    el.innerHTML = '<div class="quote-card"><div class="quote-card-inner"><div class="label">Error</div><div class="meta" style="color:var(--red);margin-top:6px">' + escapeHtml(data.error) + '</div></div></div>';
    badge.style.display = 'none';
    return;
  }
  const quotes = data.data?.quotes || [];
  if (!quotes.length) {
    el.innerHTML = '<div class="quote-card"><div class="quote-card-inner"><div class="label">No quotes</div><div class="meta" style="margin-top:6px">No solver available for this route.</div></div></div>';
    badge.style.display = 'none';
    return;
  }
  const q = quotes[0];
  const safeQuoteId = escapeHtml(q.quoteId);
  badge.style.display = 'inline';
  el.innerHTML =
    '<div class="quote-card">' +
      '<div class="quote-card-inner"><div class="label">Route</div>' +
      '<div class="meta" style="margin-top:6px">' + escapeHtml(capitalize(intent.from)) + ' → ' + escapeHtml(capitalize(intent.to)) + '</div></div>' +
    '</div>' +
    '<div class="quote-card">' +
      '<div class="quote-card-inner"><div class="label">You Send</div>' +
      '<div class="value value-dim">' + escapeHtml(q.inputAmount) + '</div></div>' +
    '</div>' +
    '<div class="quote-card quote-card-highlight">' +
      '<div class="quote-card-inner"><div class="label">You Receive</div>' +
      '<div class="value">' + escapeHtml(q.outputAmount) + '</div>' +
      '<div class="meta">Quote ID: ' + safeQuoteId + ' <button class="copy-btn" onclick="copyQuoteId(this.getAttribute(\'data-id\'),this)" data-id="' + safeQuoteId + '">Copy</button></div></div>' +
    '</div>';
}

async function compareQuotes() {
  const text = document.getElementById('intentInput').value;
  const intent = parseIntent(text);
  if (!intent || !intent.from) { setStatus('Enter intent with source chain. Try: send 10 USDC from Ethereum', 'err'); return; }

  setStatus('<span class="loading"></span> Comparing quotes across chains…', 'ok');
  showSkeleton('compareResult');

  try {
    const url = '/api/compare?from_chain=' + intent.from + '&token=' + intent.token + '&amount=' + intent.amount;
    const res = await fetch(url);
    const data = await res.json();
    renderCompare(data.data || [], intent);
    refreshTraces();
  } catch (e) {
    setStatus('Compare failed: ' + escapeHtml(e.message), 'err');
  }
}

function renderCompare(results, intent) {
  const el = document.getElementById('compareResult');
  setStatus('', '');
  if (!results.length) {
    el.innerHTML = '<p class="empty-state">No quotes available for comparison.</p>';
    return;
  }
  let maxIdx = 0;
  results.forEach((r, i) => {
    if (parseFloat(r.output) > parseFloat(results[maxIdx].output)) maxIdx = i;
  });
  let html = '<table class="compare-table"><thead><tr><th>Destination</th><th>Output</th><th>Fee</th></tr></thead><tbody>';
  results.forEach((r, i) => {
    const feeAbs = Math.abs(parseFloat(r.fee_pct)).toFixed(2);
    const cls = i === maxIdx ? ' class="winner"' : '';
    html += '<tr' + cls + '><td>' + escapeHtml(capitalize(intent.from)) + ' → ' + escapeHtml(capitalize(r.chain)) + '</td><td>' + escapeHtml(r.output) + '</td><td class="compare-fee">~' + escapeHtml(feeAbs) + '%</td></tr>';
  });
  html += '</tbody></table>';
  el.innerHTML = html;
}

async function refreshTraces() {
  try {
    const res = await fetch('/api/traces');
    const data = await res.json();
    const el = document.getElementById('traces');
    const badge = document.getElementById('traceBadge');
    const traces = data.traces || [];
    if (!traces.length) return;
    // Deduplicate consecutive steps with same tool and same error
    const deduped = [];
    for (const t of traces) {
      const prev = deduped[deduped.length - 1];
      const isError = t.result_summary.startsWith('Error');
      if (prev && prev.tool === t.tool && prev.isError && isError && prev.result_summary === t.result_summary) {
        prev.count++;
      } else {
        deduped.push({ ...t, isError, count: 1 });
      }
    }
    badge.textContent = deduped.length + ' steps' + (deduped.length < traces.length ? ' (' + traces.length + ' total)' : '');
    el.innerHTML = deduped.map(t => {
      const dur = t.duration_ms === 0 ? '⚡ cached' : escapeHtml(t.duration_ms) + 'ms';
      const countBadge = t.count > 1 ? '<span class="trace-count">×' + escapeHtml(t.count) + '</span>' : '';
      return '<div class="trace-item">' +
        '<span class="trace-tool">⚡ ' + escapeHtml(t.tool) + '</span>' +
        '<span class="trace-result ' + (t.isError ? 'trace-error' : '') + '">' + escapeHtml(t.result_summary) + countBadge + '</span>' +
        '<span class="trace-duration">' + dur + '</span>' +
      '</div>';
    }).join('');
  } catch (e) {}
}

function copyQuoteId(id, btn) {
  navigator.clipboard.writeText(id).then(() => {
    btn.textContent = 'Copied';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 1500);
  });
}

document.getElementById('intentInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') submitIntent();
});

function truncateAddr(addr) {
  if (!addr || addr.length < 12) return addr || '?';
  return addr.slice(0, 6) + '…' + addr.slice(-4);
}

function renderSolvers(data) {
  const el = document.getElementById('solverResult');
  const badge = document.getElementById('solverBadge');
  const solvers = data?.data?.solvers || data?.solvers || [];
  if (!solvers.length && !data?.data?.solverIdentities) {
    el.innerHTML = '<p class="empty-state">No solver data available. The endpoint may require an API key.</p>';
    badge.textContent = '0 solvers';
    document.getElementById('statSolvers').textContent = '0';
    return;
  }
  const identities = data?.data?.solverIdentities || solvers;
  const count = identities.length;
  badge.textContent = count + ' solver' + (count !== 1 ? 's' : '');
  document.getElementById('statSolvers').textContent = count;
  let html = '<div class="solver-grid">';
  identities.forEach((s, i) => {
    const name = s.solverName || s.name || truncateAddr(s.address || s.solverAddress || '');
    const addr = s.address || s.solverAddress || '';
    const chains = s.supportedChains || s.chains || [];
    const chainBadges = chains.map(c => '<span class="solver-chain-badge">' + escapeHtml(c) + '</span>').join('');
    const delay = (i * 0.06).toFixed(2);
    html += '<div class="solver-card" style="animation-delay:' + delay + 's">' +
      '<div class="solver-card-header">' +
        '<span class="solver-status"></span>' +
        '<span class="solver-name" title="' + escapeHtml(addr || name) + '">' + escapeHtml(name) + '</span>' +
      '</div>' +
      '<div class="solver-chains">' + (chainBadges || '<span class="solver-chain-badge">unknown</span>') + '</div>' +
    '</div>';
  });
  html += '</div>';
  el.innerHTML = html;
}

async function refreshSolvers() {
  const el = document.getElementById('solverResult');
  el.innerHTML = '<div class="skeleton w60"></div><div class="skeleton w80"></div>';
  try {
    const res = await fetch('/api/solvers');
    const data = await res.json();
    renderSolvers(data);
  } catch (e) {
    el.innerHTML = '<p class="empty-state" style="color:var(--red)">Failed to load solvers: ' + escapeHtml(e.message) + '</p>';
  }
}

async function loadRoutes() {
  try {
    const res = await fetch('/api/routes');
    const data = await res.json();
    const count = data.data?.count || 0;
    document.getElementById('statRoutes').textContent = count;
  } catch (e) {}
}

// Load routes on startup
fetch('/api/routes').then(r => r.json()).then(d => {
  const count = d.data?.count || 0;
  if (count > 0) {
    setStatus('Connected to LI.FI Intents MCP · ' + count + ' routes available', 'ok');
    document.getElementById('statRoutes').textContent = count;
    setTimeout(() => setStatus('', ''), 3000);
  }
}).catch(() => {});

// Load solvers and stats on startup
refreshSolvers();

async function refreshSolverStats() {
  const chartEl = document.getElementById('chainBarChart');
  chartEl.innerHTML = '<div class="skeleton w60"></div><div class="skeleton w80"></div><div class="skeleton w40"></div>';
  document.getElementById('analyticsBadge').textContent = 'loading…';
  try {
    const res = await fetch('/api/solver-stats');
    const data = await res.json();
    document.getElementById('anTotal').textContent = data.totalSolvers;
    document.getElementById('anActive').textContent = data.activeSolvers;
    document.getElementById('anRoutes').textContent = data.routesCovered;
    document.getElementById('anAvgTime').textContent = data.avgResponseTime || '—';
    document.getElementById('analyticsBadge').textContent = data.totalSolvers + ' solvers';

    const dist = data.chainDistribution || {};
    const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]);
    if (entries.length === 0) {
      chartEl.innerHTML = '<p class="empty-state">No chain distribution data available.</p>';
      return;
    }
    const maxVal = entries[0][1];
    let html = '';
    entries.forEach(([chain, count], i) => {
      const pct = maxVal > 0 ? Math.max(4, (count / maxVal) * 100) : 4;
      const delay = (i * 0.05).toFixed(2);
      html += '<div class="chain-bar-row" style="animation-delay:' + delay + 's">' +
        '<span class="chain-bar-label">' + escapeHtml(chain) + '</span>' +
        '<div class="chain-bar-track">' +
          '<div class="chain-bar-fill" style="width:' + pct + '%">' +
            '<span class="chain-bar-count">' + escapeHtml(count) + '</span>' +
          '</div>' +
        '</div>' +
      '</div>';
    });
    chartEl.innerHTML = html;
  } catch (e) {
    chartEl.innerHTML = '<p class="empty-state" style="color:var(--red)">Failed to load stats: ' + escapeHtml(e.message) + '</p>';
    document.getElementById('analyticsBadge').textContent = 'error';
  }
}

// Load analytics on startup
refreshSolverStats();

// Transaction Tracker
async function trackOrder() {
  const input = document.getElementById('orderIdInput');
  const orderId = input.value.trim();
  if (!orderId) return;
  const el = document.getElementById('trackerResult');
  const badge = document.getElementById('trackerBadge');
  badge.textContent = 'tracking...';
  el.innerHTML = '<p style="color:var(--text-muted)">⏳ Tracking order ' + orderId + '...</p>';
  try {
    const res = await fetch('/api/track-order?order_id=' + encodeURIComponent(orderId));
    const data = await res.json();
    badge.textContent = data?.data?.status || 'unknown';
    const status = (data?.data?.status || 'unknown').toLowerCase();
    const statusColor = status === 'completed' ? 'var(--green)' : status === 'failed' ? 'var(--red)' : 'var(--accent)';
    const steps = [
      { name: 'Created', done: true },
      { name: 'Pending', done: ['pending','filling','completed'].includes(status) },
      { name: 'Filling', done: ['filling','completed'].includes(status) },
      { name: 'Completed', done: status === 'completed' },
    ];
    if (status === 'failed') {
      steps.push({ name: 'Failed', done: true, failed: true });
    }
    let html = '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:12px 0">';
    steps.forEach((s, i) => {
      const color = s.failed ? 'var(--red)' : s.done ? 'var(--green)' : 'var(--text-muted)';
      html += '<span style="color:' + color + ';font-weight:' + (s.done ? '600' : '400') + '">' + (s.done ? '●' : '○') + ' ' + s.name + '</span>';
      if (i < steps.length - 1) html += '<span style="color:var(--text-muted)">→</span>';
    });
    html += '</div>';
    if (data?.data) {
      html += '<div style="font-size:13px;color:var(--text-secondary);margin-top:8px">';
      html += '<div>Order ID: <code>' + (data.data.id || orderId) + '</code></div>';
      if (data.data.createdAt) html += '<div>Created: ' + new Date(data.data.createdAt).toLocaleString() + '</div>';
      html += '</div>';
    }
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = '<p style="color:var(--red)">✗ Error: ' + e.message + '</p>';
    badge.textContent = 'error';
  }
}

// Load recent orders
async function loadRecentOrders() {
  const el = document.getElementById('recentOrders');
  try {
    const res = await fetch('/api/recent-orders');
    const data = await res.json();
    const orders = data?.data?.orders || [];
    if (!orders.length) {
      el.innerHTML = '<div class="analytics-section-title">Recent Orders</div><p class="empty-state">No recent orders. Execute a transfer to create one.</p>';
      return;
    }
    let html = '<div class="analytics-section-title">Recent Orders</div>';
    html += '<table class="compare-table"><thead><tr><th>Order ID</th><th>Status</th><th>Created</th></tr></thead><tbody>';
    orders.forEach(o => {
      const status = (o.status || 'unknown').toLowerCase();
      const color = status === 'completed' ? 'var(--green)' : status === 'failed' ? 'var(--red)' : 'var(--accent)';
      html += '<tr><td><code>' + (o.id || '?').substring(0, 12) + '...</code></td>';
      html += '<td style="color:' + color + '">' + (o.status || '?') + '</td>';
      html += '<td>' + (o.createdAt ? new Date(o.createdAt).toLocaleString() : '—') + '</td></tr>';
    });
    html += '</tbody></table>';
    el.innerHTML = html;
    document.getElementById('trackerBadge').textContent = orders.length + ' orders';
  } catch (e) {
    el.innerHTML = '<div class="analytics-section-title">Recent Orders</div><p class="empty-state">Failed to load orders.</p>';
  }
}

loadRecentOrders();

// Load quote statistics
async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    document.getElementById('statTotal').textContent = data.total || 0;
    document.getElementById('statAvgFee').textContent = data.avg_fee ? data.avg_fee.toFixed(3) + '%' : '—';
    
    if (data.top_routes && data.top_routes.length > 0) {
      const [from, to, count] = data.top_routes[0];
      document.getElementById('statTopRoute').textContent = `${from}→${to}`;
      document.getElementById('statsBadge').textContent = `${data.total} quotes`;
    }
    
    if (data.top_tokens && data.top_tokens.length > 0) {
      const [token, count] = data.top_tokens[0];
      document.getElementById('statTopToken').textContent = token.toUpperCase();
    }
  } catch (e) {
    console.error('Failed to load stats:', e);
  }
}

loadStats();

// Solver Tools: Route Health Checker
async function checkRouteHealth() {
  const fromChain = document.getElementById('healthFromChain').value;
  const toChain = document.getElementById('healthToChain').value;
  const el = document.getElementById('healthResult');
  el.innerHTML = '<div class="skeleton w60"></div>';
  try {
    const res = await fetch('/api/route-health?from_chain=' + fromChain + '&to_chain=' + toChain);
    const data = await res.json();
    const healthy = data?.data?.healthy;
    const status = healthy === true ? 'healthy' : healthy === false ? 'unhealthy' : 'unknown';
    const dotColor = status === 'healthy' ? 'green' : status === 'unhealthy' ? 'red' : 'amber';
    const label = status === 'healthy' ? 'Route Healthy' : status === 'unhealthy' ? 'Route Unhealthy' : 'Status Unknown';
    const fromLabel = document.getElementById('healthFromChain').selectedOptions[0].text;
    const toLabel = document.getElementById('healthToChain').selectedOptions[0].text;
    let meta = '';
    if (data?.data?.latencyMs != null) meta += '<div class="health-meta">Latency: <code>' + escapeHtml(data.data.latencyMs) + 'ms</code></div>';
    if (data?.data?.activeSolvers != null) meta += '<div class="health-meta">Active Solvers: <code>' + escapeHtml(data.data.activeSolvers) + '</code></div>';
    if (data?.data?.lastChecked) meta += '<div class="health-meta">Last Checked: <code>' + escapeHtml(new Date(data.data.lastChecked).toLocaleString()) + '</code></div>';
    if (data?.error) meta += '<div class="health-meta" style="color:var(--red)">Error: ' + escapeHtml(data.error) + '</div>';
    el.innerHTML = '<div class="health-card ' + status + '">' +
      '<div class="health-status">' +
        '<span class="health-dot ' + dotColor + '"></span>' +
        '<span class="health-label">' + escapeHtml(label) + '</span>' +
      '</div>' +
      '<div class="health-meta">' + escapeHtml(fromLabel) + ' → ' + escapeHtml(toLabel) + '</div>' +
      meta +
    '</div>';
  } catch (e) {
    el.innerHTML = '<div class="health-card unhealthy"><div class="health-status"><span class="health-dot red"></span><span class="health-label">Request Failed</span></div><div class="health-meta">' + escapeHtml(e.message) + '</div></div>';
  }
}

// Solver Tools: Quote Inventory Viewer
async function viewInventory() {
  const fromChain = document.getElementById('invFromChain').value;
  const toChain = document.getElementById('invToChain').value;
  const fromAsset = document.getElementById('invFromToken').value;
  const toAsset = document.getElementById('invToToken').value;
  const el = document.getElementById('inventoryResult');
  el.innerHTML = '<div class="skeleton w60"></div><div class="skeleton w80"></div>';
  try {
    const res = await fetch('/api/solver-inventory?from_chain=' + fromChain + '&to_chain=' + toChain + '&from_asset=' + encodeURIComponent(fromAsset) + '&to_asset=' + encodeURIComponent(toAsset));
    const data = await res.json();
    const quotes = data?.data?.quotes || data?.data?.inventory || [];
    if (!quotes.length) {
      const err = data?.error || data?.message || 'No standing quotes found for this route.';
      el.innerHTML = '<div class="inventory-card"><div class="inventory-row"><span class="inventory-key">Result</span><span class="inventory-val" style="color:var(--text-muted)">' + escapeHtml(err) + '</span></div></div>';
      return;
    }
    let html = '';
    quotes.slice(0, 10).forEach(function(q, i) {
      const fromLabel = document.getElementById('invFromChain').selectedOptions[0].text;
      const toLabel = document.getElementById('invToChain').selectedOptions[0].text;
      html += '<div class="inventory-card" style="animation-delay:' + (i * 0.06).toFixed(2) + 's">';
      html += '<div class="inventory-row"><span class="inventory-key">Route</span><span class="inventory-val">' + escapeHtml(fromLabel) + ' → ' + escapeHtml(toLabel) + '</span></div>';
      if (q.solver || q.solverName) html += '<div class="inventory-row"><span class="inventory-key">Solver</span><span class="inventory-val">' + escapeHtml(q.solver || q.solverName) + '</span></div>';
      if (q.inputAmount) html += '<div class="inventory-row"><span class="inventory-key">Input</span><span class="inventory-val">' + escapeHtml(q.inputAmount) + '</span></div>';
      if (q.outputAmount) html += '<div class="inventory-row"><span class="inventory-key">Output</span><span class="inventory-val">' + escapeHtml(q.outputAmount) + '</span></div>';
      if (q.margin || q.fee) html += '<div class="inventory-row"><span class="inventory-key">Margin</span><span class="inventory-val">' + escapeHtml(q.margin || q.fee) + '</span></div>';
      if (q.minAmount) html += '<div class="inventory-row"><span class="inventory-key">Min Amount</span><span class="inventory-val">' + escapeHtml(q.minAmount) + '</span></div>';
      if (q.maxAmount) html += '<div class="inventory-row"><span class="inventory-key">Max Amount</span><span class="inventory-val">' + escapeHtml(q.maxAmount) + '</span></div>';
      html += '</div>';
    });
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = '<div class="inventory-card"><div class="inventory-row"><span class="inventory-key">Error</span><span class="inventory-val" style="color:var(--red)">' + escapeHtml(e.message) + '</span></div></div>';
  }
}
</script>
</body>
</html>"""
