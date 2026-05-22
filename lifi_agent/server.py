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
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace; background: #0d1117; color: #e6edf3; min-height: 100vh; }
  .container { max-width: 1000px; margin: 0 auto; padding: 24px; }
  header { text-align: center; padding: 32px 0 24px; border-bottom: 1px solid #30363d; margin-bottom: 24px; }
  header h1 { font-size: 28px; color: #58a6ff; font-weight: 700; }
  header p { color: #8b949e; margin-top: 8px; font-size: 14px; }
  .input-row { display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }
  .input-row input, .input-row select { background: #161b22; border: 1px solid #30363d; color: #e6edf3; padding: 10px 14px; border-radius: 8px; font-size: 14px; font-family: monospace; }
  .input-row input { flex: 1; min-width: 200px; }
  .input-row select { min-width: 120px; }
  .btn { background: #238636; color: #fff; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; }
  .btn:hover { background: #2ea043; }
  .btn:disabled { background: #21262d; color: #484f58; cursor: not-allowed; }
  .btn-secondary { background: #21262d; border: 1px solid #30363d; }
  .btn-secondary:hover { background: #30363d; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
  @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
  .panel { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; }
  .panel h3 { color: #58a6ff; font-size: 16px; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
  .panel h3 .badge { background: #238636; color: #fff; font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 400; }
  .quote-card { background: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
  .quote-card .label { color: #8b949e; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
  .quote-card .value { font-size: 24px; font-weight: 700; color: #3fb950; margin: 4px 0; }
  .quote-card .meta { color: #8b949e; font-size: 13px; }
  .trace-item { display: flex; gap: 12px; padding: 10px 0; border-bottom: 1px solid #21262d; font-size: 13px; }
  .trace-item:last-child { border-bottom: none; }
  .trace-tool { color: #d29922; font-weight: 600; min-width: 160px; }
  .trace-duration { color: #8b949e; min-width: 60px; text-align: right; }
  .trace-result { color: #3fb950; flex: 1; }
  .trace-error { color: #f85149; }
  .status { padding: 8px 12px; border-radius: 8px; font-size: 13px; margin-bottom: 16px; }
  .status.ok { background: #23863620; color: #3fb950; border: 1px solid #23863640; }
  .status.err { background: #f8514920; color: #f85149; border: 1px solid #f8514940; }
  .loading { display: inline-block; width: 16px; height: 16px; border: 2px solid #30363d; border-top-color: #58a6ff; border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .compare-table { width: 100%; border-collapse: collapse; }
  .compare-table th { text-align: left; color: #8b949e; font-size: 12px; padding: 8px; border-bottom: 1px solid #30363d; }
  .compare-table td { padding: 8px; font-size: 14px; border-bottom: 1px solid #21262d; }
  .compare-table tr:first-child td { color: #3fb950; font-weight: 600; }
  .footer { text-align: center; padding: 24px 0; color: #484f58; font-size: 12px; border-top: 1px solid #21262d; margin-top: 24px; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>LI.FI Intents × AI Agent</h1>
    <p>Cross-chain operations via natural language · Powered by MCP Protocol</p>
  </header>

  <div class="input-row">
    <input type="text" id="intentInput" placeholder="send 10 USDC from Base to Arbitrum" />
    <button class="btn" id="submitBtn" onclick="submitIntent()">Get Quote</button>
    <button class="btn btn-secondary" onclick="compareQuotes()">Compare</button>
  </div>

  <div id="status"></div>

  <div class="grid">
    <div class="panel">
      <h3>Quote Result <span class="badge" id="quoteBadge" style="display:none">LIVE</span></h3>
      <div id="quoteResult">
        <p style="color:#484f58">Enter an intent to get a cross-chain quote from the solver network.</p>
      </div>
    </div>

    <div class="panel">
      <h3>Agent Reasoning <span class="badge" id="traceBadge">0 steps</span></h3>
      <div id="traces">
        <p style="color:#484f58">Agent tool calls will appear here in real-time.</p>
      </div>
    </div>
  </div>

  <div class="panel" style="margin-top:24px">
    <h3>Route Comparison</h3>
    <div id="compareResult">
      <p style="color:#484f58">Click "Compare" to see quotes across multiple destination chains.</p>
    </div>
  </div>

  <div class="footer">
    <p>Built for LI.FI Intents Builder Challenge · <a href="https://docs.li.fi/lifi-intents/introduction" style="color:#58a6ff">Docs</a> · <a href="https://github.com/tiyadegure/lifi-intents-demo" style="color:#58a6ff">GitHub</a></p>
  </div>
</div>

<script>
const chains = ['ethereum','base','arbitrum','optimism','polygon','bsc'];
const tokens = ['USDC','USDT','ETH'];

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

async function submitIntent() {
  const text = document.getElementById('intentInput').value;
  const intent = parseIntent(text);
  if (!intent) { setStatus('Could not parse intent. Try: send 10 USDC from Base to Arbitrum', 'err'); return; }
  if (!intent.from || !intent.to) { setStatus('Need two chains. Supported: ' + chains.join(', '), 'err'); return; }

  document.getElementById('submitBtn').disabled = true;
  setStatus('<span class="loading"></span> Querying solver network...', 'ok');

  try {
    const url = '/api/quote?from_chain=' + intent.from + '&to_chain=' + intent.to + '&token=' + intent.token + '&amount=' + intent.amount;
    const res = await fetch(url);
    const data = await res.json();
    renderQuote(data, intent);
    refreshTraces();
  } catch (e) {
    setStatus('Request failed: ' + e.message, 'err');
  }
  document.getElementById('submitBtn').disabled = false;
}

function renderQuote(data, intent) {
  const el = document.getElementById('quoteResult');
  const badge = document.getElementById('quoteBadge');
  if (data.error) {
    el.innerHTML = '<div class="quote-card"><div class="label">Error</div><div class="meta" style="color:#f85149">' + data.error + '</div></div>';
    badge.style.display = 'none';
    return;
  }
  const quotes = data.data?.quotes || [];
  if (!quotes.length) {
    el.innerHTML = '<div class="quote-card"><div class="label">No quotes</div><div class="meta">No solver available for this route.</div></div>';
    badge.style.display = 'none';
    return;
  }
  const q = quotes[0];
  badge.style.display = 'inline';
  el.innerHTML =
    '<div class="quote-card">' +
      '<div class="label">Route</div>' +
      '<div class="meta">' + intent.from.charAt(0).toUpperCase() + intent.from.slice(1) + ' → ' + intent.to.charAt(0).toUpperCase() + intent.to.slice(1) + '</div>' +
    '</div>' +
    '<div class="quote-card">' +
      '<div class="label">You Send</div>' +
      '<div class="value" style="color:#e6edf3">' + q.inputAmount + '</div>' +
    '</div>' +
    '<div class="quote-card">' +
      '<div class="label">You Receive</div>' +
      '<div class="value">' + q.outputAmount + '</div>' +
      '<div class="meta">Quote ID: ' + q.quoteId + '</div>' +
    '</div>';
}

async function compareQuotes() {
  const text = document.getElementById('intentInput').value;
  const intent = parseIntent(text);
  if (!intent || !intent.from) { setStatus('Enter intent with source chain. Try: send 10 USDC from Ethereum', 'err'); return; }

  setStatus('<span class="loading"></span> Comparing quotes across chains...', 'ok');

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
    el.innerHTML = '<p style="color:#484f58">No quotes available for comparison.</p>';
    return;
  }
  let html = '<table class="compare-table"><tr><th>Destination</th><th>Output</th><th>Fee</th></tr>';
  results.forEach((r, i) => {
    html += '<tr><td>' + intent.from.charAt(0).toUpperCase() + intent.from.slice(1) + ' → ' +
      r.chain.charAt(0).toUpperCase() + r.chain.slice(1) + '</td><td>' + r.output + '</td><td>~' + Math.abs(parseFloat(r.fee_pct)).toFixed(2) + '%</td></tr>';
  });
  html += '</table>';
  el.innerHTML = html;
}

async function refreshTraces() {
  try {
    const res = await fetch('/api/traces');
    const data = await res.json();
    const el = document.getElementById('traces');
    const badge = document.getElementById('traceBadge');
    const traces = data.traces || [];
    badge.textContent = traces.length + ' steps';
    if (!traces.length) return;
    el.innerHTML = traces.map(t =>
      '<div class="trace-item">' +
        '<span class="trace-tool">⚡ ' + t.tool + '</span>' +
        '<span class="trace-result ' + (t.result_summary.startsWith('Error') ? 'trace-error' : '') + '">' + t.result_summary + '</span>' +
        '<span class="trace-duration">' + t.duration_ms + 'ms</span>' +
      '</div>'
    ).join('');
  } catch (e) {}
}

document.getElementById('intentInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') submitIntent();
});

// Load routes on startup
fetch('/api/routes').then(r => r.json()).then(d => {
  const count = d.data?.count || 0;
  if (count > 0) {
    setStatus('Connected to LI.FI Intents MCP · ' + count + ' routes available', 'ok');
    setTimeout(() => setStatus('', ''), 3000);
  }
}).catch(() => {});
</script>
</body>
</html>"""
