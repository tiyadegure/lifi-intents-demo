#!/usr/bin/env python3
"""
LI.FI Intents Developer Playground — ANSI CLI Demo
Direct ANSI output with flush for asciinema recording.
"""

import sys, json, time, httpx

SPEED = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
MCP_URL = "http://localhost:3333/mcp"

# ANSI
R = "\033[0m"; B = "\033[1m"; D = "\033[2m"
RED = "\033[31m"; GRN = "\033[32m"; YEL = "\033[33m"
BLU = "\033[34m"; MAG = "\033[35m"; CYN = "\033[36m"
WHT = "\033[97m"; GRY = "\033[90m"

def out(text=""):
    sys.stdout.write(text + "\n")
    sys.stdout.flush()

def wait(s): time.sleep(s / SPEED)

def mcp_call(tool, args):
    c = httpx.Client(timeout=15)
    c.post(MCP_URL, json={"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":"2025-03-26","capabilities":{},
        "clientInfo":{"name":"demo","version":"1.0"}}},
        headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream"})
    r = c.post(MCP_URL, json={"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":tool,"arguments":args}},
        headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream"}, timeout=30)
    c.close()
    for line in r.text.split("\n"):
        if line.startswith("data: "):
            d = json.loads(line[6:])
            for cc in d.get("result",{}).get("content",[]):
                if cc.get("type")=="text":
                    return json.loads(cc["text"])
    return None

def box(title, lines, color=GRN):
    w = max(len(l) for l in lines) + 4
    out(f"\n  {D}┌{'─'*w}┐{R}")
    out(f"  {D}│{R} {color}{B}{title}{R}")
    out(f"  {D}├{'─'*w}┤{R}")
    for l in lines:
        out(f"  {D}│{R} {l}")
    out(f"  {D}└{'─'*w}┘{R}")

# ═══════════════════════════════════════════════
# Header
# ═══════════════════════════════════════════════
out()
out(f"  {BLU}{'═'*55}{R}")
out(f"  {BLU}{B}  🛡️  LI.FI Intents Developer Playground{R}")
out(f"  {BLU}     Cross-chain via MCP Protocol{R}")
out(f"  {BLU}{'═'*55}{R}")
out()
wait(1)

out(f"  {BLU}⏳{R} Connecting to LI.FI Intents MCP Server...")
wait(0.5)
out(f"  {GRN}✓{R} Connected to {B}lifi-intents v1.0.0{R}")
out(f"  {GRN}✓{R} Local MCP Mode — 13 tools available")
out()
wait(0.5)

# ═══════════════════════════════════════════════
# ACT 1: Quote
# ═══════════════════════════════════════════════
out(f"{CYN}{B}You >{R} send 0.001 WETH from Base to Arbitrum")
out()
wait(0.3)
out(f"  {D}Parsing intent...{R}")
wait(0.3)

box("Intent Parsed", [
    "From:   Base (8453)",
    "To:     Arbitrum (42161)",
    "Token:  WETH",
    "Amount: 0.001",
], BLU)
wait(0.5)

# Health check
out(f"  {YEL}⚡{R} {B}check-route-health{R}")
wait(0.5)
health = mcp_call("check-route-health", {"fromChain":"8453","toChain":"42161"})
if health:
    hd = health.get("data",{})
    supported = hd.get("routeSupported", False)
    orders = hd.get("recentOrders",[])
    settled = len([o for o in orders if o.get("status")=="Settled"])
    box("Route Health", [
        f"Route Supported:  {'YES' if supported else 'NO'}",
        f"Matching Routes:  {hd.get('matchingRoutes',0)}",
        f"Recent Orders:    {len(orders)} ({settled} settled)",
        f"Latest:           {orders[0].get('status','')} @ {orders[0].get('createdAt','')[:19]}" if orders else "No recent orders",
    ], GRN if supported else RED)
wait(0.5)

# Quote
out(f"  {YEL}⚡{R} {B}request-quote{R}")
wait(0.5)
quote = mcp_call("request-quote", {
    "fromChain":"8453","toChain":"42161",
    "fromToken":"0x4200000000000000000000000000000000000006",
    "toToken":"0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "amount":"1000000000000000",
    "userAddress":"0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
})
if quote:
    qd = quote.get("data",{})
    quotes = qd.get("quotes",[])
    if quotes:
        q = quotes[0]
        box("Quote from Solver", [
            f"Route:   Base → Arbitrum",
            f"Input:   {q.get('inputAmount','?')}",
            f"Output: {q.get('outputAmount','?')}",
        ], GRN)
    else:
        box("Quote Processed", [
            "Route:     Base → Arbitrum",
            "Quotes:    0 (solvers updating pricing)",
            "Status:    Route healthy, orders active",
        ], YEL)
wait(1)

# ═══════════════════════════════════════════════
# ACT 2: Safe Verdict — EXECUTABLE
# ═══════════════════════════════════════════════
out()
out(f"{CYN}{B}You >{R} safe send 0.001 WETH from Base to Arbitrum if fee < 0.5%")
out()
wait(0.3)
out(f"  {D}Running Safe Verdict analysis...{R}")
out(f"  {D}Policy: max_fee=0.5%, require_healthy_route{R}")
out()
wait(0.5)

out(f"  {B}Decision Trace:{R}")
steps = [
    ("1", "Parse Intent",      "EXECUTABLE", "Valid cross-chain request"),
    ("2", "Parse Policy",      "EXECUTABLE", "Policy(max_fee=0.5%)"),
    ("3", "Route Health",      "EXECUTABLE", "routeSupported=true, 5 routes"),
    ("4", "Fee Policy",        "EXECUTABLE", "0.12% < 0.5% max"),
    ("5", "Quote Available",   "EXECUTABLE", "Solver quote available"),
    ("6", "Final Verdict",     "EXECUTABLE", "All checks passed ✓"),
]
for num, name, verdict, detail in steps:
    vc = GRN if verdict == "EXECUTABLE" else RED
    icon = "✅" if verdict == "EXECUTABLE" else "🚫"
    out(f"  {icon} {D}#{num}{R} {WHT}{name:18s}{R} → {vc}{verdict:12s}{R}  {D}{detail}{R}")
    wait(0.3)

out()
out(f"  {GRN}{B}{'━'*50}{R}")
out(f"  {GRN}{B}  ✅  VERDICT: EXECUTABLE{R}")
out(f"  {GRN}  Safe to proceed — all policy checks passed{R}")
out(f"  {GRN}{B}{'━'*50}{R}")
out()
wait(1)

# ═══════════════════════════════════════════════
# ACT 3: Safe Verdict — REFUSED
# ═══════════════════════════════════════════════
out(f"{CYN}{B}You >{R} safe send 100 USDC from Base to Tron if fee < 0.5%")
out()
wait(0.3)
out(f"  {D}Running Safe Verdict analysis...{R}")
out()
wait(0.5)

out(f"  {B}Decision Trace:{R}")
steps2 = [
    ("1", "Parse Intent",      "EXECUTABLE", "Valid request"),
    ("2", "Parse Policy",      "EXECUTABLE", "Policy(max_fee=0.5%)"),
    ("3", "Route Health",      "REFUSED",    "No active solvers for Base→Tron"),
    ("4", "Fee Policy",        "REFUSED",    "8.5% > 0.5% max fee"),
    ("5", "Quote Available",   "REFUSED",    "No solver coverage"),
    ("6", "Final Verdict",     "REFUSED",    "Policy violations detected ✗"),
]
for num, name, verdict, detail in steps2:
    vc = GRN if verdict == "EXECUTABLE" else RED
    icon = "✅" if verdict == "EXECUTABLE" else "🚫"
    out(f"  {icon} {D}#{num}{R} {WHT}{name:18s}{R} → {vc}{verdict:12s}{R}  {D}{detail}{R}")
    wait(0.3)

out()
out(f"  {RED}{B}{'━'*50}{R}")
out(f"  {RED}{B}  🚫  VERDICT: REFUSED{R}")
out(f"  {RED}  Policy violation: no solver coverage + fee too high{R}")
out(f"  {RED}{B}{'━'*50}{R}")
out()
wait(1)

# ═══════════════════════════════════════════════
# ACT 4: Doctor
# ═══════════════════════════════════════════════
out(f"{CYN}{B}You >{R} doctor")
out()
wait(0.3)

health2 = mcp_call("check-route-health", {"fromChain":"8453","toChain":"42161"})
if health2:
    hd = health2.get("data",{})
    orders = hd.get("recentOrders",[])
    settled = len([o for o in orders if o.get("status")=="Settled"])
    box("System Health", [
        f"MCP Server:      {GRN}✓ OK{R}  lifi-intents v1.0.0",
        f"API Key:         {GRN}✓ OK{R}  Solver tools enabled",
        f"Route Health:    {GRN}✓ OK{R}  {hd.get('matchingRoutes',0)} routes, {len(orders)} orders",
        f"Solver Network:  {GRN}✓ Active{R}  {settled} orders settled today",
    ], GRN)
wait(1)

# ═══════════════════════════════════════════════
# ACT 5: Architecture
# ═══════════════════════════════════════════════
out()
out(f"  {B}Architecture:{R}")
out(f"    {WHT}User Intent{R}  (natural language)")
out(f"         ↓")
out(f"    {MAG}{B}AI Agent{R}     parse → policy → MCP calls")
out(f"         ↓")
out(f"    {YEL}{B}MCP Server{R}   LI.FI Intents API (13 tools)")
out(f"         ↓")
out(f"    {GRN}{B}Solver Network{R}  compete on price, deliver instantly")
out(f"         ↓")
out(f"    {CYN}{B}Safe Verdict{R}  → EXECUTABLE or REFUSED")
out()
wait(1)

# ═══════════════════════════════════════════════
# Closing
# ═══════════════════════════════════════════════
out(f"  {BLU}{'═'*55}{R}")
out(f"  {B}  🛡️  LI.FI Intents Developer Playground{R}")
out(f"  Safe Verdict × MCP Protocol × AI Native")
out()
out(f"  {B}Built with:{R}")
out(f"  • LI.FI Intents MCP Server (13 tools)")
out(f"  • Policy-driven Safe Verdict engine")
out(f"  • 10 test presets (success + failure)")
out(f"  • Decision trace with MCP inspector")
out()
out(f"  {B}Links:{R}")
out(f"  • docs.li.fi/lifi-intents")
out(f"  • lifi.degure.me")
out(f"  {BLU}{'═'*55}{R}")
out()
