# LI.FI Intents × Safe Verdict — X Thread

> 用法：主贴发 Tweet 1，然后在主贴下面评论 Tweet 2-5。
> 视频文件：`remotion/output/demo-v5.2.mp4`

---

## Tweet 1（主贴 — quote-tweet 官方推文时用这段）

```
🛡️ Built a Safe Verdict Playground for @LI_FI Intents Builder Challenge!

Type a cross-chain intent in natural language, get an EXECUTABLE or REFUSED verdict with full decision trace.

"send 0.001 WETH from Base to Arbitrum only if route is healthy and fee < 0.5%"

→ MCP Server + Web UI + CLI
→ 366 tests passing
→ Real solver quotes, not mocks

🔗 Live: lifi.degure.me
📦 Code: github.com/tiyadegure/lifi-intents-demo

[附视频 demo-v5.2.mp4]
```

---

## Tweet 2（评论 1 — 问题）

```
🤔 Problem: Cross-chain is complex.

You need to know chains, tokens, gas, routes, fees… and hope nothing goes wrong.

What if an AI Agent could check everything for you — and only proceed when it's actually safe?
```

---

## Tweet 3（评论 2 — 解决方案 + 架构）

```
💡 Safe Verdict Pipeline:

Natural language input
  → Parse intent + extract policy constraints
    → MCP tools: get-supported-routes, check-route-health, request-quote
      → Policy engine: fee limits, route health, chain restrictions
        → Verdict: EXECUTABLE ✅ or REFUSED 🚫

Every step is logged in a Decision Trace with tool names and timing.
```

---

## Tweet 4（评论 3 — 功能亮点）

```
✨ What's built:

• 🌐 Web UI — 3-column layout, 10 presets, MCP proof panel
• 💻 CLI — interactive terminal with rich output
• 🔌 Local MCP Server — real connection to LI.FI Intents API
• 🛡️ Policy Engine — fee limits, route health, chain filters
• 📊 Decision Trace — full audit log with timing
• 🧪 366 tests — parser, policies, verdicts, API
```

---

## Tweet 5（评论 4 — 结尾 + 链接）

```
🎯 Why this matters:

AI Agents need safe, auditable cross-chain decisions — not just "get me a quote."

LI.FI Intents MCP makes this possible. This project shows how to build on it.

🔗 Live demo: lifi.degure.me
📦 Source: github.com/tiyadegure/lifi-intents-demo
📝 Pitfalls doc: 10 real gotchas building against LI.FI Intents

Thanks @LI_FI for the Intents MCP! 🙌

#LI_FI #Intents #AI #CrossChain #MCP
```

---

## 发布步骤

1. **5/26 周二 21:00 北京时间** — 等官方 launch tweet
2. **Quote-tweet** 官方推文，用 Tweet 1 内容 + 附视频
3. **评论** Tweet 2-5（依次回复主贴）
4. **填写提交表单**（链接等官方发布）
