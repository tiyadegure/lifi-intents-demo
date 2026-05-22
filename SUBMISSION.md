# LI.FI Intents × AI Agent - 提交材料

## 项目名称
LI.FI Intents × AI Agent: Safe Verdict — 策略驱动的跨链安全裁决

## 一句话描述
用自然语言定义跨链策略，AI Agent 自动检查路由、费用、健康状态，给出 EXECUTABLE 或 REFUSED 裁决

## 项目亮点
1. **Safe Verdict 引擎** - 策略驱动的安全裁决，不是简单报价
2. **AI 意图解析** - 自然语言 → 跨链操作 + 策略约束
3. **MCP 协议集成** - 直接调用 LI.FI Intents
4. **完整工具链** - Web UI + CLI + SDK
5. **Solver 生态** - Route Health、Quote Inventory、Become a Solver

## 核心功能：Safe Verdict
```
用户输入: "send 10 USDC from Base to Arbitrum only if fee < 0.5%"

解析结果:
  - Intent: 10 USDC base → arbitrum
  - Policy: fee < 0.5%

Safe Verdict Pipeline:
  ✓ Route Supported: base → arbitrum (USDC)
  ✓ Route Health: Skipped (not required by policy)
  ✓ Quote Received: Output: 9.98 USDC
  ✓ Fee Calculated: 0.18%
  ✓ Fee Policy: Fee 0.18% ≤ limit 0.5%

Verdict: EXECUTABLE

Reason:
  This intent satisfies the user policy. Fee 0.18% is within acceptable limits.
```

## 技术架构
```
User Input (自然语言 + 策略)
     ↓
Parse Intent + Policy
     ↓
┌─────────────────────────────────────┐
│  Safe Verdict Pipeline              │
│  ┌─────────────────────────────────┐│
│  │ 1. Check Supported Route        ││
│  │ 2. Check Route Health (if req)  ││
│  │ 3. Request Quote                ││
│  │ 4. Calculate Fee                ││
│  │ 5. Check Policy Constraints     ││
│  └─────────────────────────────────┘│
│                                     │
│  Decision Engine                    │
│  ┌─────────────────────────────────┐│
│  │ EXECUTABLE or REFUSED           ││
│  │ + Detailed Reasoning            ││
│  └─────────────────────────────────┘│
└─────────────────────────────────────┘
```

## 功能列表
- ✅ 自然语言意图解析（"send 10 USDC from Base to Arbitrum"）
- ✅ MCP 协议集成（LI.FI Intents）
- ✅ Web UI Dashboard（报价历史、统计面板）
- ✅ Solver Tools（Route Health、Quote Inventory、Become a Solver）
- ✅ CLI 交互界面（send、compare、route health、routes、stats 等）
- ✅ Python SDK（pip install lifi-agent）
- ✅ 多链报价对比
- ✅ 交易追踪

## 演示链接
- **Web UI**: http://143.198.95.119:8888
- **GitHub**: https://github.com/tiyadegure/lifi-intents-demo
- **Demo 视频**: output/demo_v2.mp4

## 使用方式
```bash
# 安装
pip install lifi-agent

# CLI 使用
python -m lifi_agent
> send 10 USDC from Base to Arbitrum
> compare 50 USDC from Base to Polygon
> route health base

# Web UI
python -m lifi_agent.server
# 打开 http://localhost:8888
```

## 为什么这个项目重要？
1. **降低门槛** - 不需要懂链、代币、Gas，自然语言就能跨链
2. **AI 原生** - 符合 AI Agent 时代趋势
3. **MCP 标准** - 可以集成到任何 AI 助手（Claude、GPT、Hermes）
4. **Solver 机会** - 展示了 Solver 生态的可能性

## 提交清单
- [x] 代码（GitHub）
- [x] Demo 视频
- [x] Web UI 演示
- [ ] X Thread（待发布）
- [ ] 提交表单（5/26 开放）
