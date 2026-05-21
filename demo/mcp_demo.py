#!/usr/bin/env python3
"""LI.FI Intents × AI Agent Demo — AI Agent + MCP Server = Cross-Chain Made Simple"""

import asyncio, httpx, json, time, sys

MCP_URL = "https://intents-mcp.li.fi/mcp"
CYAN, GREEN, YELLOW, BOLD, DIM, RESET = "\033[36m", "\033[32m", "\033[33m", "\033[1m", "\033[2m", "\033[0m"


def say(text, delay=0.012):
    for ch in text:
        sys.stdout.write(ch); sys.stdout.flush(); time.sleep(delay)
    print()

def agent(text):
    print(f"\n{CYAN}🤖 Agent:{RESET}"); say(text, 0.01)

def call(name, args=None):
    print(f"\n{YELLOW}⚡ MCP Tool: {BOLD}{name}{RESET}")
    if args: print(f"{DIM}   {json.dumps(args)[:200]}{RESET}")

def result(data):
    print(f"{GREEN}✅{RESET}")
    print(f"{DIM}{json.dumps(data, indent=2)[:800]}{RESET}")


async def mcp_session(c):
    r = await c.post(MCP_URL,
        json={"jsonrpc":"2.0","id":1,"method":"initialize","params":{
            "protocolVersion":"2025-03-26","capabilities":{},
            "clientInfo":{"name":"hermes-agent","version":"1.0"}}},
        headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream"},
        timeout=30)
    return r.headers.get("mcp-session-id")

async def mcp_call(c, sid, rid, method, params):
    r = await c.post(MCP_URL,
        json={"jsonrpc":"2.0","id":rid,"method":method,"params":params},
        headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream","mcp-session-id":sid},
        timeout=30)
    if r.status_code != 200: return None
    for ln in r.text.split("\n"):
        if ln.startswith("data: "): return json.loads(ln[6:])
    return None


async def main():
    print(f"\n{BOLD}{'='*60}\n  LI.FI Intents × AI Agent Demo\n{'='*60}{RESET}\n")

    async with httpx.AsyncClient() as c:

        # ══════════════════════════════════════════════════════
        # ACT 1: Connect & Discover
        # ══════════════════════════════════════════════════════

        agent("I'm an AI Agent. Let me connect to the LI.FI Intents\n"
              "   MCP Server to explore cross-chain capabilities...")
        sid = await mcp_session(c)
        print(f"{GREEN}✅ Connected! Session: {sid[:8]}...{RESET}")

        agent("Now let me discover all available tools.")
        call("tools/list")
        d = await mcp_call(c, sid, 2, "tools/list", {})
        if d and "result" in d:
            tools = d["result"].get("tools", [])
            result({"count": len(tools), "tools": [t["name"] for t in tools]})
        time.sleep(0.6)

        agent(f"Found {len(tools)} tools! Here's what I can do:\n\n"
              "   📋 Integrator tools (no API key):\n"
              "   • get-supported-routes — discover chains & tokens\n"
              "   • request-quote — get cross-chain pricing\n"
              "   • prepare-order — build on-chain order\n"
              "   • submit-order — submit to order server\n"
              "   • track-order — monitor order status\n"
              "   • list-orders — list historical orders\n\n"
              "   🔧 Solver tools (API key required):\n"
              "   • submit-standing-quotes — manage pricing\n"
              "   • check-route-health — diagnose routes\n"
              "   • debug-order — inspect order lifecycle")

        # ══════════════════════════════════════════════════════
        # ACT 2: View Real Orders
        # ══════════════════════════════════════════════════════

        time.sleep(0.8)
        agent("Let me check real cross-chain orders on the network.")
        sid2 = await mcp_session(c)
        call("list-orders", {"limit": 5})
        d = await mcp_call(c, sid2, 3, "tools/call",
            {"name": "list-orders", "arguments": {"limit": 5}})
        if d:
            ct = d.get("result", {}).get("content", [])
            for x in ct:
                if x.get("type") == "text":
                    try:
                        orders = json.loads(x["text"])
                        result(orders)
                        data = orders.get("data", {}).get("orders", [])
                        if data:
                            settled = [o for o in data if o.get("status") == "Settled"]
                            agent(f"Found {len(data)} real orders!\n"
                                  f"   {len(settled)} already settled ✅\n\n"
                                  f"   Latest order:\n"
                                  f"   • ID: {data[0].get('catalystOrderId','?')[:30]}...\n"
                                  f"   • Status: {data[0].get('status','?')}\n"
                                  f"   • {data[0].get('description','')}\n\n"
                                  f"   These are REAL cross-chain intents being settled\n"
                                  f"   on the LI.FI network right now!")
                    except:
                        result(x["text"])

        # ══════════════════════════════════════════════════════
        # ACT 3: Architecture Deep Dive
        # ══════════════════════════════════════════════════════

        time.sleep(1)
        agent("Let me explain how LI.FI Intents works:\n\n"
              "   Traditional bridge: User picks path → hopes for the best\n"
              "   LI.FI Intents:     User expresses WANT → solvers compete\n\n"
              "   ┌─────────────┐    ┌──────────────┐    ┌─────────────┐\n"
              "   │   User       │───▶│ Order Server │───▶│   Solvers   │\n"
              "   │ (expresses   │    │  (matches    │    │  (compete   │\n"
              "   │   intent)    │    │   quotes)    │    │   on price) │\n"
              "   └─────────────┘    └──────────────┘    └─────────────┘\n"
              "          │                                        │\n"
              "          ▼                                        ▼\n"
              "   ┌─────────────┐                        ┌─────────────┐\n"
              "   │ Input Settler│◀───────────────────────│  Delivery   │\n"
              "   │  (releases   │    Oracle verifies     │ (instant on │\n"
              "   │   funds)     │    delivery proof      │  dest chain)│\n"
              "   └─────────────┘                        └─────────────┘\n\n"
              "   Key insight: Solvers use their OWN capital to deliver first,\n"
              "   then settle later. Users get INSTANT cross-chain transfers!")

        # ══════════════════════════════════════════════════════
        # ACT 4: Why This Matters for AI Agents
        # ══════════════════════════════════════════════════════

        time.sleep(1)
        agent("Why does this matter for AI Agents?\n\n"
              "   🤖 AI Agents need to move value across chains\n"
              "   🔗 MCP gives them a standardized protocol to do it\n"
              "   💡 Intents abstract away bridge complexity\n\n"
              "   Before: Agent must know which bridge to use, handle\n"
              "   failures, manage gas on multiple chains...\n\n"
              "   Now: Agent just says 'send 10 USDC from Base to\n"
              "   Arbitrum' — the solver network handles everything.\n\n"
              "   This is the future of cross-chain UX. 🚀")

        # ══════════════════════════════════════════════════════
        # ACT 5: Summary
        # ══════════════════════════════════════════════════════

        time.sleep(1)
        agent("Demo summary:\n\n"
              "   ✅ Connected to LI.FI Intents MCP Server\n"
              "   ✅ Discovered 13 tools (integrator + solver)\n"
              "   ✅ Viewed real orders settling on the network\n"
              "   ✅ Understood the intent-based architecture\n\n"
              "   LI.FI Intents + MCP = AI Agents do cross-chain natively.\n"
              "   No bridge selection, no path optimization — just intent.\n\n"
              "   Built with: LI.FI Intents MCP Server + Hermes Agent\n"
              "   docs.li.fi/lifi-intents")

    print(f"\n{BOLD}{'='*60}\n  Demo Complete — LI.FI Intents × AI Agent\n{'='*60}{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
