"""LI.FI Intents Agent — Web API server."""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json
import time

from lifi_agent.agent import LifAgent, Intent, parse_intent

app = FastAPI(title="LI.FI Intents Agent", version="1.0.0")
agent = LifAgent()

# ── Reasoning trace storage ─────────────────────────────────────────
traces: list[dict] = []


def trace_step(tool: str, args: dict, result: dict, duration_ms: int):
    """Record an agent reasoning step."""
    step = {
        "timestamp": time.time(),
        "tool": tool,
        "args": args,
        "result_summary": _summarize_result(result),
        "duration_ms": duration_ms,
    }
    traces.append(step)
    if len(traces) > 100:
        traces.pop(0)
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
        try:
            agent.connect()
        except Exception as e:
            print(f"MCP connect failed: {e}")


@app.get("/api/routes")
async def get_routes():
    ensure_connected()
    start = time.time()
    result = agent.get_routes()
    duration = int((time.time() - start) * 1000)
    trace_step("get-supported-routes", {}, result, duration)
    return result


@app.get("/api/quote")
async def get_quote(from_chain: str, to_chain: str, token: str, amount: str):
    ensure_connected()
    start = time.time()
    try:
        intent = parse_intent(f"send {amount} {token} from {from_chain} to {to_chain}")
        result = agent.get_quote(intent)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    duration = int((time.time() - start) * 1000)
    trace_step("request-quote", {
        "from": from_chain, "to": to_chain, "token": token, "amount": amount
    }, result, duration)
    return result


@app.get("/api/compare")
async def compare_quotes(from_chain: str, token: str, amount: str):
    ensure_connected()
    start = time.time()
    try:
        intent = parse_intent(f"send {amount} {token} from {from_chain} to ethereum")
        results = agent.compare_quotes(intent)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    duration = int((time.time() - start) * 1000)
    trace_step("compare-quotes", {
        "from": from_chain, "token": token, "amount": amount
    }, {"data": results}, duration)
    return {"data": results}


@app.get("/api/traces")
async def get_traces():
    return {"traces": traces[-20:]}


@app.get("/api/favorites")
async def get_favorites():
    return {"favorites": agent.get_favorite_routes()}


@app.get("/api/solvers")
async def get_solvers():
    ensure_connected()
    start = time.time()
    result = agent.get_solver_identities()
    duration = int((time.time() - start) * 1000)
    trace_step("get-solver-identities", {}, result, duration)
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
  }
  @media(max-width:420px){
    header h1{font-size:20px}
    header p{font-size:12px}
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

  <div class="footer">
    <p>Built for LI.FI Intents Builder Challenge · <a href="https://docs.li.fi/lifi-intents/introduction">Docs</a> · <a href="https://github.com/tiyadegure/lifi-intents-demo">GitHub</a></p>
  </div>
</div>

<script>
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
    setStatus('Request failed: ' + e.message, 'err');
  }
  document.getElementById('submitBtn').disabled = false;
}

function renderQuote(data, intent) {
  const el = document.getElementById('quoteResult');
  const badge = document.getElementById('quoteBadge');
  if (data.error) {
    el.innerHTML = '<div class="quote-card"><div class="quote-card-inner"><div class="label">Error</div><div class="meta" style="color:var(--red);margin-top:6px">' + data.error + '</div></div></div>';
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
  badge.style.display = 'inline';
  el.innerHTML =
    '<div class="quote-card">' +
      '<div class="quote-card-inner"><div class="label">Route</div>' +
      '<div class="meta" style="margin-top:6px">' + capitalize(intent.from) + ' → ' + capitalize(intent.to) + '</div></div>' +
    '</div>' +
    '<div class="quote-card">' +
      '<div class="quote-card-inner"><div class="label">You Send</div>' +
      '<div class="value value-dim">' + q.inputAmount + '</div></div>' +
    '</div>' +
    '<div class="quote-card quote-card-highlight">' +
      '<div class="quote-card-inner"><div class="label">You Receive</div>' +
      '<div class="value">' + q.outputAmount + '</div>' +
      '<div class="meta">Quote ID: ' + q.quoteId + ' <button class="copy-btn" onclick="copyQuoteId(\'' + q.quoteId + '\',this)">Copy</button></div></div>' +
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
    setStatus('Compare failed: ' + e.message, 'err');
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
    html += '<tr' + cls + '><td>' + capitalize(intent.from) + ' → ' + capitalize(r.chain) + '</td><td>' + r.output + '</td><td class="compare-fee">~' + feeAbs + '%</td></tr>';
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
      const dur = t.duration_ms === 0 ? '⚡ cached' : t.duration_ms + 'ms';
      const countBadge = t.count > 1 ? '<span class="trace-count">×' + t.count + '</span>' : '';
      return '<div class="trace-item">' +
        '<span class="trace-tool">⚡ ' + t.tool + '</span>' +
        '<span class="trace-result ' + (t.isError ? 'trace-error' : '') + '">' + t.result_summary + countBadge + '</span>' +
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
    const chainBadges = chains.map(c => '<span class="solver-chain-badge">' + c + '</span>').join('');
    const delay = (i * 0.06).toFixed(2);
    html += '<div class="solver-card" style="animation-delay:' + delay + 's">' +
      '<div class="solver-card-header">' +
        '<span class="solver-status"></span>' +
        '<span class="solver-name" title="' + (addr || name) + '">' + name + '</span>' +
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
    el.innerHTML = '<p class="empty-state" style="color:var(--red)">Failed to load solvers: ' + e.message + '</p>';
  }
}

async function loadStats() {
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
</script>
</body>
</html>"""
