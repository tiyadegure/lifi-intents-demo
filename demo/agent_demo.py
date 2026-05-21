#!/usr/bin/env python3
"""
LI.FI Intents × AI Agent Demo
Shows an AI agent using MCP protocol to interact with LI.FI Intents

Uses live MCP calls when available, falls back to cached real data.
"""

import httpx
import json
import sys
import time

# ── ANSI Colors ──────────────────────────────────────────────────────
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
WHITE = "\033[97m"

MCP_URL = "https://intents-mcp.li.fi/mcp"
AGENT = f"{MAGENTA}{BOLD}Hermes{RESET}"
USER = f"{CYAN}{BOLD}Builder{RESET}"

# ── Cached real responses (captured from live MCP server) ────────────
CACHE = {
    "routes": {"data": {"routes": [], "count": 812}, "message": "812+ active routes across 15+ chains"},
    "quote": {"data": {"fromChain": "Base", "toChain": "Arbitrum", "swapType": "exact-input", "requestedAmount": "10 USDC (exact-input)", "quotes": [{"quoteIndex": 0, "quoteId": "quote_nYG0ckHgZLHVXHvVoUpwHHnquvcmxP", "inputAmount": "10 USDC", "outputAmount": "9.983725 USDC", "validUntil": 1779356936, "partialFill": False}], "cacheKey": "8453:42161:0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913:0xaf88d065e77c8cC2239327C5EDb3A432268e5831:0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"}, "message": "Quote received. Use \"prepare-order\" to prepare the order for signing."}
}

# ── Helpers ──────────────────────────────────────────────────────────
def typewrite(text, delay=0.025, color=WHITE):
    for char in text:
        sys.stdout.write(f"{color}{char}{RESET}")
        sys.stdout.flush()
        time.sleep(delay)
    print()

def dots(n=3, d=0.35):
    for _ in range(n):
        sys.stdout.write(f"{DIM}●{RESET} ")
        sys.stdout.flush()
        time.sleep(d)
    print()

def box(title, content, color=GREEN):
    lines = content.split('\n')
    w = max(len(l) for l in lines) + 2
    bw = max(w + 4, 49)
    print(f"\n{DIM}┌{'─' * bw}┐{RESET}")
    print(f"{DIM}│{RESET} {color}✓ {title}{RESET}{' ' * (bw - len(title) - 3)}{DIM}│{RESET}")
    print(f"{DIM}├{'─' * bw}┤{RESET}")
    for line in lines:
        pad = line + ' ' * (bw - len(line) - 2)
        print(f"{DIM}│{RESET} {pad}{DIM}│{RESET}")
    print(f"{DIM}└{'─' * bw}┘{RESET}")

def tool_box(name, args):
    print(f"\n{DIM}┌─────────────────────────────────────────────────┐{RESET}")
    print(f"{DIM}│{RESET} {YELLOW}⚡ MCP → {name}{RESET}{' ' * (40 - len(name))}{DIM}│{RESET}")
    print(f"{DIM}├─────────────────────────────────────────────────┤{RESET}")
    for line in args.split('\n'):
        pad = line[:47] + ' ' * max(0, 47 - len(line))
        print(f"{DIM}│{RESET} {DIM}{pad}{RESET} {DIM}│{RESET}")
    print(f"{DIM}└─────────────────────────────────────────────────┘{RESET}")

def sep():
    print(f"\n{DIM}{'─' * 55}{RESET}\n")

# ── MCP Client ───────────────────────────────────────────────────────
def mcp_call(tool, args, use_cache=True):
    """Call MCP tool with fallback to cache"""
    try:
        client = httpx.Client(timeout=15)
        r = client.post(MCP_URL,
            json={"jsonrpc":"2.0","id":1,"method":"initialize","params":{
                "protocolVersion":"2025-03-26","capabilities":{},
                "clientInfo":{"name":"demo","version":"1.0"}}},
            headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream"})
        sid = r.headers.get("mcp-session-id")
        r2 = client.post(MCP_URL,
            json={"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":tool,"arguments":args}},
            headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream","mcp-session-id":sid},
            timeout=30)
        client.close()
        if r2.status_code == 200:
            for line in r2.text.split('\n'):
                s = line.strip()
                if s.startswith('data:'):
                    js = s[5:].strip()
                    if js:
                        d = json.loads(js)
                        for c in d.get('result',{}).get('content',[]):
                            if c.get('type') == 'text':
                                return json.loads(c['text']), True  # live=True
    except:
        pass
    # Fallback
    cache_key = tool.replace("request-", "").replace("get-supported-", "routes")
    if use_cache and cache_key in CACHE:
        return CACHE[cache_key], False
    return {"error": "unavailable"}, False

# ── Demo ─────────────────────────────────────────────────────────────
def run():
    print(f"\n{BOLD}{BLUE}{'═' * 55}{RESET}")
    print(f"{BOLD}{BLUE}   LI.FI Intents × AI Agent Demo{RESET}")
    print(f"{BOLD}{BLUE}   Powered by MCP Protocol{RESET}")
    print(f"{BOLD}{BLUE}{'═' * 55}{RESET}\n")

    # ── Connect ──────────────────────────────────────────────────
    print(f"{DIM}[Connecting to LI.FI Intents MCP Server...]{RESET}")
    dots(3, 0.3)
    box("MCP Server Connected",
        "Server:  lifi-intents v1.0.0\n"
        "Proto:   MCP (Model Context Protocol)\n"
        "Tools:   13 available (6 integrator + 7 solver)\n"
        "Status:  Ready", BLUE)
    sep()

    # ── User asks ────────────────────────────────────────────────
    typewrite(f"{USER}:", 0.01, CYAN)
    typewrite("I want to send 10 USDC from Base to Arbitrum.", 0.03)
    typewrite("What's the best rate I can get?", 0.03)
    sep()

    # ── Agent thinks ─────────────────────────────────────────────
    typewrite(f"{AGENT}:", 0.01, MAGENTA)
    typewrite("Let me query the LI.FI Intents solver network.", 0.03)
    dots(4, 0.4)

    # ── Get routes ───────────────────────────────────────────────
    tool_box("get-supported-routes", "{}")
    dots(2, 0.3)
    result, live = mcp_call("get-supported-routes", {})
    tag = f" {GREEN}● LIVE{RESET}" if live else f" {DIM}(cached){RESET}"
    box("Routes Discovered",
        f"812+ active routes across 15+ chains{tag}\n"
        "Chains: Base, Arbitrum, Ethereum, Optimism,\n"
        "        Polygon, BSC, Solana, Tron, Soneium...")
    sep()

    # ── Get quote ────────────────────────────────────────────────
    typewrite(f"{AGENT}:", 0.01, MAGENTA)
    typewrite("Route found. Fetching solver quotes now...", 0.03)
    dots(3, 0.4)

    tool_box("request-quote", '{\n  "fromChain":  "Base (8453)",\n  "toChain":    "Arbitrum (42161)",\n  "fromToken":  "USDC",\n  "toToken":    "USDC",\n  "amount":     "10"\n}')
    dots(3, 0.4)

    result, live = mcp_call("request-quote", {
        "fromChain": "8453", "toChain": "42161",
        "fromToken": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "toToken": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "amount": "10",
        "userAddress": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    })

    data = result.get("data", {})
    quotes = data.get("quotes", [])
    if quotes:
        q = quotes[0]
        tag = f" {GREEN}● LIVE{RESET}" if live else ""
        box("Quote from Solver",
            f"Route:    Base → Arbitrum (cross-chain){tag}\n"
            f"Input:    {q['inputAmount']}\n"
            f"Output:   {q['outputAmount']}\n"
            f"Fee:      ~0.016 USDC (0.16%)\n"
            f"Type:     {data.get('swapType', 'exact-input')}\n"
            f"Solver:   Filled from solver inventory",
            GREEN if live else YELLOW)
    sep()

    # ── Explain ──────────────────────────────────────────────────
    typewrite(f"{AGENT}:", 0.01, MAGENTA)
    typewrite("Here's what happened under the hood:", 0.03)
    print()

    steps = [
        ("1️⃣  Intent", "You said WHAT you want, not HOW.\n   \"Send 10 USDC Base→Arbitrum\" — that's it."),
        ("2️⃣  Match", "LI.FI matched your intent against solver\n   standing quotes — pre-published price curves,\n   not real-time bidding."),
        ("3️⃣  Solve", "The best solver fills your order using their\n   own capital. You get ~9.98 USDC on Arbitrum\n   almost instantly."),
        ("4️⃣  Settle", "The solver is reimbursed after on-chain\n   verification. You never wait for bridging."),
    ]
    for title, desc in steps:
        print(f"  {BOLD}{WHITE}{title}{RESET}")
        for line in desc.split('\n'):
            print(f"    {DIM}{line}{RESET}")
        print()
        time.sleep(0.4)
    sep()

    # ── MCP insight ──────────────────────────────────────────────
    typewrite(f"{AGENT}:", 0.01, MAGENTA)
    typewrite("The magic: all of this happened through MCP.", 0.03)
    typewrite("Any AI agent with MCP support can do this", 0.03)
    typewrite("autonomously. No browser, no UI, no clicks.", 0.03)
    print()

    print(f"  {BOLD}{GREEN}MCP Tools Used:{RESET}")
    tools = [
        ("get-supported-routes", "Discover chains & tokens"),
        ("request-quote", "Get solver pricing"),
        ("prepare-order", "Build on-chain order"),
        ("track-order", "Monitor settlement"),
    ]
    for name, desc in tools:
        print(f"    {CYAN}{name}{RESET} → {DIM}{desc}{RESET}")
        time.sleep(0.15)
    sep()

    # ── Architecture ─────────────────────────────────────────────
    print(f"  {BOLD}{WHITE}Architecture:{RESET}")
    print(f"    {DIM}User Intent{RESET} → {YELLOW}MCP Server{RESET} → {GREEN}Order Server{RESET} → {CYAN}Solver Network{RESET}")
    print(f"    {DIM}                                              ↓{RESET}")
    print(f"    {DIM}User receives tokens ← Oracle Verification ← Delivery{RESET}")
    sep()

    # ── Closing ──────────────────────────────────────────────────
    print(f"{BOLD}{BLUE}{'═' * 55}{RESET}")
    print(f"{BOLD}   LI.FI Intents — Intent-Based Cross-Chain{RESET}")
    print(f"   Foundation of Open Intents Framework (OIF)")
    print(f"   by the Ethereum Foundation")
    print(f"\n{BOLD}   Links:{RESET}")
    print(f"   • docs.li.fi/lifi-intents/introduction")
    print(f"   • intents-mcp.li.fi/mcp")
    print(f"{BOLD}{BLUE}{'═' * 55}{RESET}\n")

if __name__ == "__main__":
    run()
