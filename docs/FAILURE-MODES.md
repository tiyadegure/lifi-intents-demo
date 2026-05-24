# Failure Modes

Common failure scenarios and how to diagnose them.

---

## 1. Local MCP not running

**Symptom:** `doctor` shows `mock_fallback` mode, or strict mode raises `ConnectError`.

**Check:**
```bash
python -m lifi_agent doctor
```

**Expected output (if down):**
```
Mode: mock_fallback
  MCP endpoint reachable: Mock mode active (mock_fallback)
[Warning] Mock fallback active: Local MCP at http://localhost:3333/mcp was unreachable
[Next] Start the local MCP server at http://localhost:3333/mcp, or set LIFI_AGENT_MOCK_MODE=1
```

**Fix:**
```bash
cd lifi-intents-mcp && npm start
```

**Verify:**
```bash
curl -s http://localhost:3333/mcp -X POST \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```
Should return HTTP 200 with server info.

---

## 2. Solver temporarily returns no quotes

**Symptom:** `request-quote` returns empty `quotes: []` even though route is supported.

**Check:**
```bash
python -m lifi_agent doctor
```

**Expected output:**
```
Quotes
  ✓ request-quote: Output: (empty)
  ✗ Solver Response: No quotes for 1 USDC Base→Arbitrum
[Next] Solvers may be temporarily offline. Wait a few minutes and retry, or use mock mode
```

**Diagnosis:**
- Solver uptime varies by chain pair. Base→Arbitrum is usually reliable; Base→zkSync may have gaps.
- This is a **solver-side** issue, not a code bug.
- `get-supported-routes` may still return the route as "supported" even when no solver is actively quoting.

**Workaround:**
- Wait 5-10 minutes and retry
- Try a different chain pair
- Use `LIFI_AGENT_MOCK_MODE=1` for demo purposes

---

## 3. Strict mode raises error

**Symptom:** `RuntimeError: LIFI_AGENT_STRICT_MODE=1: refusing to use mock mode` or `ConnectError`.

**Cause:** `LIFI_AGENT_STRICT_MODE=1` is set but local MCP is unreachable.

**Check:**
```bash
echo $LIFI_AGENT_STRICT_MODE  # should be "1"
echo $LIFI_AGENT_MOCK_MODE    # should be empty
curl -s http://localhost:3333/mcp  # should return something
```

**Fix options:**
1. Start the local MCP server (preferred)
2. Unset strict mode: `unset LIFI_AGENT_STRICT_MODE`
3. If both `LIFI_AGENT_STRICT_MODE=1` and `LIFI_AGENT_MOCK_MODE=1` are set, you get a conflict error. Unset one.

---

## 4. Mock fallback triggered unexpectedly

**Symptom:** `doctor` shows `mock_fallback` instead of `local_mcp`.

**Diagnosis flow:**
1. Is local MCP running? `curl http://localhost:3333/mcp`
2. Is `LIFI_MCP_URL` set to a different URL? `echo $LIFI_MCP_URL`
3. Is there a firewall/port issue? `ss -tlnp | grep 3333`

**Expected behavior:** When local MCP is unreachable, the client:
1. Tries to connect
2. Catches `ConnectError` or `TimeoutException`
3. Sets `_mock_mode = True` and `_mock_fallback = True`
4. Returns mock data transparently

**This is by design.** Mock fallback ensures the CLI always works. Set `LIFI_AGENT_STRICT_MODE=1` if you need to guarantee real data.

---

## Quick reference

| Scenario | Mode | doctor shows | Fix |
|---|---|---|---|
| Local MCP running | `local_mcp` | All green | None needed |
| MCP down, auto-fallback | `mock_fallback` | Warning: mock fallback | Start MCP server |
| `MOCK_MODE=1` set | `mock_forced` | Mock Source: env var | Unset env var |
| `STRICT_MODE=1`, MCP down | error | ConnectError raised | Start MCP or unset strict |
| Both strict + mock | error | RuntimeError | Unset one |
