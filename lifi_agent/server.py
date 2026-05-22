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
            "fromChain": intent.from_chain_id(),
            "toChain": intent.to_chain_id(),
            "fromToken": intent.from_token_address(),
            "toToken": intent.to_token_address(),
            "amount": intent.amount,
        },
        "verdict": result.verdict,
        "reason": result.reason,
        "steps": steps,
        "total_duration_ms": result.total_duration_ms,
    }


# ── Web UI ──────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LI.FI Intents Developer Playground</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
  *{margin:0;padding:0;box-sizing:border-box}
  :root{
    --bg:#060a13;--surface:#0c1220;--card:#111a2e;--card-hover:#162040;
    --border:#1e2d4a;--border-subtle:#162040;
    --text:#e8edf5;--text2:#8494b2;--text3:#4a5a7a;
    --accent:#6c5ce7;--accent2:#4f8cff;--glow:#6c5ce733;
    --green:#00d68f;--green-bg:#00d68f15;--green-border:#00d68f33;
    --red:#ff6b6b;--red-bg:#ff6b6b15;--red-border:#ff6b6b33;
    --amber:#ffa94d;--amber-bg:#ffa94d15;--amber-border:#ffa94d33;
    --r:12px;--r-sm:8px;
    --mono:'JetBrains Mono','SF Mono',Consolas,monospace;
  }
  body{font-family:'Inter',-apple-system,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;-webkit-font-smoothing:antialiased}
  .container{max-width:1200px;margin:0 auto;padding:24px 20px}

  /* Header */
  header{text-align:center;padding:32px 0 24px;position:relative}
  header::after{content:'';position:absolute;bottom:0;left:50%;transform:translateX(-50%);width:160px;height:1px;background:linear-gradient(90deg,transparent,var(--accent),transparent)}
  h1{font-size:28px;font-weight:700;background:linear-gradient(135deg,#a78bfa,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;letter-spacing:-0.5px}
  header p{color:var(--text2);margin-top:8px;font-size:14px}
  .badge-row{display:flex;gap:8px;justify-content:center;margin-top:12px;flex-wrap:wrap}
  .badge{font-size:10px;padding:3px 10px;border-radius:20px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;background:var(--glow);color:var(--accent);border:1px solid #6c5ce744}

  /* Input Section */
  .input-section{margin:28px 0 24px}
  .input-row{display:flex;gap:10px;align-items:stretch}
  .input-row input{flex:1;background:var(--surface);border:1px solid var(--border);color:var(--text);padding:14px 18px;border-radius:var(--r-sm);font-size:14px;font-family:inherit;outline:none;transition:border-color .2s,box-shadow .2s}
  .input-row input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--glow)}
  .input-row input::placeholder{color:var(--text3)}
  .btn{background:linear-gradient(135deg,var(--accent),#5a4bd1);color:#fff;border:none;padding:14px 28px;border-radius:var(--r-sm);cursor:pointer;font-size:14px;font-weight:600;font-family:inherit;transition:transform .1s,box-shadow .2s,opacity .2s;white-space:nowrap}
  .btn:hover{box-shadow:0 4px 20px var(--glow);transform:translateY(-1px)}
  .btn:active{transform:translateY(0)}
  .btn:disabled{opacity:.45;cursor:not-allowed;transform:none;box-shadow:none}
  .preset-section{margin-top:12px}
  .preset-label{font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:8px}
  .presets{display:flex;gap:8px;flex-wrap:wrap}
  .preset-btn{background:var(--surface);border:1px solid var(--border-subtle);color:var(--text2);padding:6px 14px;border-radius:16px;font-size:12px;cursor:pointer;font-family:inherit;transition:all .15s;font-weight:500}
  .preset-btn.safe:hover{border-color:var(--green-border);color:var(--green);background:var(--green-bg)}
  .preset-btn.refuse:hover{border-color:var(--red-border);color:var(--red);background:var(--red-bg)}
  .preset-btn.safe.active{border-color:var(--green-border);color:var(--green);background:var(--green-bg)}
  .preset-btn.refuse.active{border-color:var(--red-border);color:var(--red);background:var(--red-bg)}

  /* Three Column Layout */
  .columns{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;margin-top:24px}
  .col{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:24px;min-height:300px;transition:border-color .2s}
  .col:hover{border-color:#2a3f6a}
  .col-header{display:flex;align-items:center;gap:10px;margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid var(--border-subtle)}
  .col-icon{font-size:20px}
  .col-title{font-size:14px;font-weight:600;color:var(--text);letter-spacing:-0.2px}
  .col-subtitle{font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:0.8px;font-weight:600}

  /* Column 1: Intent */
  .intent-json{background:var(--card);border:1px solid var(--border-subtle);border-radius:var(--r-sm);padding:16px;font-family:var(--mono);font-size:12px;line-height:1.7;color:var(--text2);overflow-x:auto;white-space:pre-wrap;word-break:break-all}
  .json-key{color:var(--accent2)}
  .json-str{color:var(--green)}
  .json-num{color:var(--amber)}

  /* Column 2: Structured Output */
  .param-group{margin-bottom:16px}
  .param-label{font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:8px}
  .param-block{background:var(--card);border:1px solid var(--border-subtle);border-radius:var(--r-sm);padding:14px;font-family:var(--mono);font-size:12px;line-height:1.6;color:var(--text2)}
  .param-block .key{color:var(--accent2)}
  .param-block .val{color:var(--green)}
  .param-block .num{color:var(--amber)}

  /* Column 3: Decision Trace */
  .trace-steps{display:flex;flex-direction:column;gap:0}
  .trace-step{display:flex;align-items:flex-start;gap:12px;padding:12px 0;border-bottom:1px solid var(--border-subtle);animation:fadeSlideIn .3s ease both}
  .trace-step:last-child{border-bottom:none}
  .trace-icon{width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;flex-shrink:0;margin-top:1px}
  .trace-icon.pass{background:var(--green-bg);color:var(--green);border:1px solid var(--green-border)}
  .trace-icon.fail{background:var(--red-bg);color:var(--red);border:1px solid var(--red-border)}
  .trace-icon.skip{background:var(--amber-bg);color:var(--amber);border:1px solid var(--amber-border)}
  .trace-body{flex:1;min-width:0}
  .trace-name{font-size:13px;font-weight:600;color:var(--text);margin-bottom:2px}
  .trace-detail{font-size:12px;color:var(--text2);line-height:1.4}
  .trace-time{font-size:11px;color:var(--text3);font-variant-numeric:tabular-nums;white-space:nowrap;margin-top:1px}

  /* Verdict Banner */
  .verdict{margin-top:20px;padding:16px 20px;border-radius:var(--r-sm);display:flex;align-items:center;gap:14px;animation:fadeSlideIn .4s ease}
  .verdict.executable{background:var(--green-bg);border:1px solid var(--green-border)}
  .verdict.refused{background:var(--red-bg);border:1px solid var(--red-border)}
  .verdict-icon{font-size:24px}
  .verdict-label{font-size:20px;font-weight:700;letter-spacing:-0.3px}
  .verdict.executable .verdict-label{color:var(--green)}
  .verdict.refused .verdict-label{color:var(--red)}
  .verdict-reason{font-size:13px;color:var(--text2);margin-top:2px}

  /* Empty State */
  .empty-state{color:var(--text3);font-size:13px;padding:40px 20px;text-align:center;line-height:1.6}
  .empty-state .icon{font-size:32px;margin-bottom:12px;display:block}

  /* Skeleton */
  .skeleton{background:linear-gradient(90deg,var(--card) 25%,var(--card-hover) 50%,var(--card) 75%);background-size:200% 100%;animation:pulse 1.5s ease-in-out infinite;border-radius:6px;height:14px;margin:8px 0}
  .skeleton.w60{width:60%}.skeleton.w40{width:40%}.skeleton.w80{width:80%}.skeleton.w100{width:100%}

  /* How It Works */
  .how-it-works{margin-top:32px;padding:28px;background:var(--surface);border:1px solid var(--border);border-radius:var(--r);text-align:center}
  .how-it-works h3{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;color:var(--text3);margin-bottom:20px}
  .flow{display:flex;align-items:center;justify-content:center;gap:6px;flex-wrap:wrap}
  .flow-step{display:flex;align-items:center;gap:6px;background:var(--card);border:1px solid var(--border-subtle);padding:8px 14px;border-radius:var(--r-sm);font-size:12px;color:var(--text2);font-weight:500;transition:border-color .2s}
  .flow-step:hover{border-color:#2a3f6a}
  .flow-step .step-icon{font-size:14px}
  .flow-step.highlight{border-color:var(--green-border);background:var(--green-bg);color:var(--green)}
  .flow-arrow{color:var(--text3);font-size:14px}

  /* Duration badge */
  .duration-badge{display:inline-block;background:var(--card);border:1px solid var(--border-subtle);color:var(--text3);font-size:11px;padding:2px 8px;border-radius:10px;font-family:var(--mono);font-variant-numeric:tabular-nums;margin-left:8px}

  /* Footer */
  footer{text-align:center;padding:24px 0 12px;color:var(--text3);font-size:12px;border-top:1px solid var(--border-subtle);margin-top:24px}
  footer a{color:var(--accent);text-decoration:none}
  footer a:hover{color:#a78bfa}

  /* Loading spinner */
  .loading{display:inline-block;width:14px;height:14px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite;vertical-align:middle}
  @keyframes spin{to{transform:rotate(360deg)}}
  @keyframes fadeSlideIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
  @keyframes pulse{0%,100%{opacity:.4}50%{opacity:.8}}

  /* Status message */
  .status-msg{padding:10px 16px;border-radius:var(--r-sm);font-size:13px;font-weight:500;margin-bottom:12px;display:flex;align-items:center;gap:10px;animation:fadeSlideIn .3s ease}
  .status-msg.err{background:var(--red-bg);color:var(--red);border:1px solid var(--red-border)}

  /* Responsive */
  @media(max-width:900px){
    .columns{grid-template-columns:1fr;gap:16px}
    .col{min-height:auto}
    .flow{gap:4px}
    .flow-step{padding:6px 10px;font-size:11px}
  }
  @media(max-width:480px){
    h1{font-size:22px}
    .input-row{flex-direction:column;gap:8px}
    .btn{padding:12px 20px}
    .container{padding:16px 14px}
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>LI.FI Intents Developer Playground</h1>
    <p>Solver-aware technical demo — natural language → policy-driven cross-chain verdict</p>
    <div class="badge-row">
      <span class="badge">MCP Protocol</span>
      <span class="badge">Safe Verdict</span>
      <span class="badge">Decision Trace</span>
      <span class="badge">Solver-Aware</span>
    </div>
  </header>

  <!-- Intent Input -->
  <div class="input-section">
    <div class="input-row">
      <input type="text" id="intentInput" placeholder="send 10 USDC from Base to Arbitrum only if fee < 0.5%"
             value="send 10 USDC from Base to Arbitrum only if fee < 0.5%">
      <button class="btn" id="analyzeBtn" onclick="analyzeIntent()">Analyze</button>
    </div>
    <div class="preset-section">
      <div class="preset-label">Preset Scenarios</div>
      <div class="presets">
        <button class="preset-btn safe" onclick="setPreset(this,'send 10 USDC from Base to Arbitrum')">🟢 Safe Transfer</button>
        <button class="preset-btn refuse" onclick="setPreset(this,'send 10 USDC from Base to Arbitrum only if fee < 0.01%')">🔴 Fee Too High</button>
        <button class="preset-btn safe" onclick="setPreset(this,'send 10 USDC from Base to Arbitrum require healthy route')">🟢 Healthy Route</button>
        <button class="preset-btn refuse" onclick="setPreset(this,'send 10 USDC from Base to Arbitrum avoid Base')">🔴 Avoid Chain</button>
        <button class="preset-btn safe" onclick="setPreset(this,'send 10 USDC from Base to Arbitrum min output 9.5')">🟢 Min Output</button>
        <button class="preset-btn refuse" onclick="setPreset(this,'send 10 USDC from Base to Arbitrum min output 100')">🔴 Min Too High</button>
      </div>
    </div>
  </div>

  <div id="statusArea"></div>

  <!-- Three Columns -->
  <div class="columns">
    <!-- Column 1: Intent -->
    <div class="col" id="colIntent">
      <div class="col-header">
        <span class="col-icon">📝</span>
        <div>
          <div class="col-title">Intent Input</div>
          <div class="col-subtitle">Parsed natural language</div>
        </div>
      </div>
      <div id="intentContent">
        <div class="empty-state">
          <span class="icon">💬</span>
          Type a cross-chain intent above<br>and click <strong>Analyze</strong> to see the<br>structured parsing result.
        </div>
      </div>
    </div>

    <!-- Column 2: Structured Output -->
    <div class="col" id="colOutput">
      <div class="col-header">
        <span class="col-icon">⚙️</span>
        <div>
          <div class="col-title">Structured Output</div>
          <div class="col-subtitle">MCP tool parameters</div>
        </div>
      </div>
      <div id="outputContent">
        <div class="empty-state">
          <span class="icon">🔧</span>
          The parsed intent will be<br>converted to structured MCP<br>tool call parameters here.
        </div>
      </div>
    </div>

    <!-- Column 3: Decision Trace -->
    <div class="col" id="colTrace">
      <div class="col-header">
        <span class="col-icon">🔍</span>
        <div>
          <div class="col-title">Decision Trace</div>
          <div class="col-subtitle">Solver-aware checks</div>
        </div>
      </div>
      <div id="traceContent">
        <div class="empty-state">
          <span class="icon">🛡️</span>
          Each safety check step will<br>appear here with pass/fail<br>status and details.
        </div>
      </div>
    </div>
  </div>

  <!-- How It Works -->
  <div class="how-it-works">
    <h3>How this maps to LI.FI Intents</h3>
    <div class="flow">
      <div class="flow-step"><span class="step-icon">🎯</span> User goal</div>
      <span class="flow-arrow">→</span>
      <div class="flow-step"><span class="step-icon">🧠</span> Structured intent</div>
      <span class="flow-arrow">→</span>
      <div class="flow-step"><span class="step-icon">🔌</span> MCP tool call</div>
      <span class="flow-arrow">→</span>
      <div class="flow-step"><span class="step-icon">💱</span> Solver quote</div>
      <span class="flow-arrow">→</span>
      <div class="flow-step"><span class="step-icon">📋</span> Policy check</div>
      <span class="flow-arrow">→</span>
      <div class="flow-step highlight"><span class="step-icon">🛡️</span> Safe verdict</div>
    </div>
  </div>

  <footer>
    Built for the <a href="https://lifi.notion.site/LI-FI-Intents-Mini-Builder-Challenge-366f0ff14ac78168a0cdd9f44a3c1f13" target="_blank">LI.FI Intents Builder Challenge</a>
    · <a href="https://github.com/tiyadegure/lifi-intents-demo" target="_blank">GitHub</a>
    · <a href="https://github.com/tiyadegure/lifi-intents-demo/blob/main/PITFALLS.md" target="_blank">Pitfalls</a>
  </footer>
</div>

<script>
function escapeHtml(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML}

function setPreset(btn,value){
  document.getElementById('intentInput').value=value;
  document.getElementById('intentInput').focus();
  // Highlight active preset
  document.querySelectorAll('.preset-btn').forEach(function(b){b.classList.remove('active')});
  btn.classList.add('active');
}

async function analyzeIntent(){
  const input=document.getElementById('intentInput');
  const text=input.value.trim();
  if(!text)return;

  const btn=document.getElementById('analyzeBtn');
  btn.disabled=true;
  btn.innerHTML='<span class="loading"></span>';

  // Clear status
  document.getElementById('statusArea').innerHTML='';

  // Show loading skeletons in all columns
  document.getElementById('intentContent').innerHTML=
    '<div class="skeleton w80"></div><div class="skeleton w60"></div><div class="skeleton w40"></div>';
  document.getElementById('outputContent').innerHTML=
    '<div class="skeleton w100"></div><div class="skeleton w80"></div><div class="skeleton w60"></div><div class="skeleton w100"></div>';
  document.getElementById('traceContent').innerHTML=
    '<div class="skeleton w80"></div><div class="skeleton w60"></div><div class="skeleton w80"></div>';

  try{
    const res=await fetch('/api/analyze-intent',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text:text})
    });
    const data=await res.json();

    if(data.error){
      document.getElementById('statusArea').innerHTML=
        '<div class="status-msg err">✗ '+escapeHtml(data.error)+'</div>';
      resetColumns();
      return;
    }

    renderIntent(data.intent);
    renderOutput(data.quote_params,data.policy);
    renderTrace(data.steps,data.verdict,data.reason,data.total_duration_ms);

  }catch(e){
    document.getElementById('statusArea').innerHTML=
      '<div class="status-msg err">✗ Request failed: '+escapeHtml(e.message)+'</div>';
    resetColumns();
  }finally{
    btn.disabled=false;
    btn.textContent='Analyze';
  }
}

function resetColumns(){
  document.getElementById('intentContent').innerHTML=
    '<div class="empty-state"><span class="icon">💬</span>Type a cross-chain intent above<br>and click <strong>Analyze</strong> to see the<br>structured parsing result.</div>';
  document.getElementById('outputContent').innerHTML=
    '<div class="empty-state"><span class="icon">🔧</span>The parsed intent will be<br>converted to structured MCP<br>tool call parameters here.</div>';
  document.getElementById('traceContent').innerHTML=
    '<div class="empty-state"><span class="icon">🛡️</span>Each safety check step will<br>appear here with pass/fail<br>status and details.</div>';
}

function renderIntent(intent){
  const j={amount:intent.amount,token:intent.token,from_chain:intent.from_chain,to_chain:intent.to_chain};
  const formatted=JSON.stringify(j,null,2)
    .replace(/"([^"]+)"/g,'<span class="json-key">"$1"</span>')
    .replace(/: "([^"]*?)"/g,': <span class="json-str">"$1"</span>')
    .replace(/: (\d+)/g,': <span class="json-num">$1</span>');
  document.getElementById('intentContent').innerHTML='<div class="intent-json">'+formatted+'</div>';
}

function renderOutput(params,policy){
  const nl=String.fromCharCode(10);

  // Quote params
  let paramsHtml='';
  for(const[k,v]of Object.entries(params)){
    const cls=typeof v==='number'?'num':'str';
    paramsHtml+='  <span class="key">"'+escapeHtml(k)+'"</span>: <span class="'+cls+'">"'+escapeHtml(v)+'"</span>'+nl;
  }
  let out='<div class="param-group"><div class="param-label">Quote Parameters</div>';
  out+='<div class="param-block">{'+nl+paramsHtml+'}</div></div>';

  // Policy
  let policyHtml='';
  for(const[k,v]of Object.entries(policy)){
    if(v===null||v===undefined)continue;
    const cls=typeof v==='number'?'num':'str';
    const valStr=typeof v==='object'?JSON.stringify(v):String(v);
    policyHtml+='  <span class="key">"'+escapeHtml(k)+'"</span>: <span class="'+cls+'">"'+escapeHtml(valStr)+'"</span>'+nl;
  }
  out+='<div class="param-group"><div class="param-label">Policy Constraints</div>';
  out+='<div class="param-block">{'+nl+policyHtml+'}</div></div>';

  document.getElementById('outputContent').innerHTML=out;
}

function renderTrace(steps,verdict,reason,durationMs){
  let html='<div class="trace-steps">';

  steps.forEach(function(step,i){
    const icon=step.status==='passed'?'✓':step.status==='failed'?'✗':'⊘';
    const iconClass=step.status==='passed'?'pass':step.status==='failed'?'fail':'skip';
    const delay=(i*0.08).toFixed(2);

    html+='<div class="trace-step" style="animation-delay:'+delay+'s">';
    html+='<div class="trace-icon '+iconClass+'">'+icon+'</div>';
    html+='<div class="trace-body">';
    html+='<div class="trace-name">'+escapeHtml(step.name)+'</div>';
    html+='<div class="trace-detail">'+escapeHtml(step.detail)+'</div>';
    html+='</div>';
    html+='<div class="trace-time">'+step.duration_ms+'ms</div>';
    html+='</div>';
  });

  html+='</div>';

  // Verdict banner
  const isExec=verdict==='EXECUTABLE';
  html+='<div class="verdict '+(isExec?'executable':'refused')+'">';
  html+='<div class="verdict-icon">'+(isExec?'🛡️':'🚫')+'</div>';
  html+='<div>';
  html+='<div class="verdict-label">'+escapeHtml(verdict)+'</div>';
  html+='<div class="verdict-reason">'+escapeHtml(reason||'')+'</div>';
  html+='</div>';
  html+='<span class="duration-badge">'+durationMs+'ms</span>';
  html+='</div>';

  document.getElementById('traceContent').innerHTML=html;
}

// Enter key to analyze
document.getElementById('intentInput').addEventListener('keydown',function(e){
  if(e.key==='Enter')analyzeIntent();
});
</script>
</body>
</html>"""
