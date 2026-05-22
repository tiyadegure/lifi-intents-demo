# LI.FI Intents × AI Agent - 提交材料

## 项目名称
LI.FI Intents × AI Agent: Safe Verdict — 策略驱动的跨链安全裁决

## 一句话描述
用自然语言定义跨链策略，AI Agent 自动检查路由、费用、健康状态，给出 EXECUTABLE 或 REFUSED 裁决

## 项目亮点
1. **Safe Verdict 引擎** - 策略驱动的安全裁决，不是简单报价
2. **Decision Trace** - 逐步追踪决策过程，展示 MCP 调用细节
3. **Solver-Aware Checks** - 路由健康、报价可用性、Solver 库存检查
4. **AI 意图解析** - 自然语言 → 跨链操作 + 策略约束
5. **MCP 协议集成** - 直接调用 LI.FI Intents
6. **完整工具链** - Web UI + CLI + SDK
7. **Solver 生态** - Route Health、Quote Inventory、Become a Solver

## 核心功能：Solver-Aware Checks
```
命令: solver base arbitrum USDC USDC

输出:
  Route: base → arbitrum

  Checks:
    ✗ Route Health: UNKNOWN
    ✓ Quote Availability: AVAILABLE
    ✗ Solver Inventory: EMPTY
      quote_count: 0
      quotes: []

  Summary:
    Total checks: 3
    Passed: 1
    Failed: 2
    Overall: DEGRADED
```

## Solver-Aware Checks 数据结构
```python
@dataclass
class SolverCheck:
    name: str           # "Route Health", "Quote Availability", "Solver Inventory"
    status: str         # "healthy", "active", "available", "empty", "error"
    details: Dict       # detailed information
    passed: bool        # whether check passed

@dataclass
class SolverReport:
    route: str          # "base → arbitrum"
    checks: List[SolverCheck]  # list of checks
    summary: Dict       # total_checks, passed_checks, failed_checks, overall_status
```

## 支持的 Solver 命令
- **solver base arbitrum**: 检查路由健康和报价可用性
- **solver base arbitrum USDC USDC**: 包含 Solver 库存检查
- **route health base arbitrum**: 单独检查路由健康
- **solver-check**: 别名命令
```
用户输入: "send 10 USDC from Base to Arbitrum only if fee < 0.5% avoid Ethereum"

解析结果:
  - Intent: 10 USDC base → arbitrum
  - Policy: fee < 0.5%, avoid ethereum

Decision Trace:
  ✓ Parse Intent: 10 USDC base → arbitrum
  ✓ Parse Policy: Policy(fee<0.5%, avoid ethereum)
  ✓ Check Supported Route: base → arbitrum (USDC) (986ms) via get-supported-routes
  ○ Check Route Health: Not required by policy
  ✓ Get Quote: Output: 9.98 USDC, Quote ID: abc123... (2341ms) via request-quote
  ✓ Calculate Fee: 0.18%
  ✓ Fee Policy: Fee 0.18% ≤ limit 0.5%
  ✓ Avoid Chains: Target chain arbitrum is not in avoid list

Verdict: EXECUTABLE

Reason:
  This intent satisfies the user policy. Fee 0.18% is within acceptable limits.

Total duration: 3327ms
```

## Decision Trace 数据结构
```python
@dataclass
class DecisionStep:
    name: str           # step name (e.g., "Route Supported", "Fee Policy")
    status: str         # "passed", "failed", "warning", "skipped"
    detail: str         # human-readable detail
    duration_ms: int    # time taken in milliseconds
    mcp_tool: str       # MCP tool called (if any)
    mcp_args: Dict      # MCP arguments
    mcp_result: Dict    # raw MCP result

@dataclass
class DecisionResult:
    verdict: str        # "EXECUTABLE" or "REFUSED"
    reason: str         # human-readable reason
    steps: List[DecisionStep]  # ordered list of decision steps
    intent: Intent      # parsed intent
    policy: Policy      # parsed policy
    quote_data: Dict    # raw quote data
    total_duration_ms: int  # total time taken
```

## 支持的自然语言策略
- **费用限制**: "only if fee < 0.5%", "fee under 1%", "max fee 0.3%"
- **路由健康**: "only if route is healthy", "healthy route"
- **避免链**: "avoid Ethereum", "avoid eth and polygon"
- **偏好**: "prefer cheapest route", "cheapest route"
- **报价要求**: "do not execute if no quote", "no quote = no execute"
- **跨链限制**: "same chain only", "no cross-chain"
- **输出限制**: "output >= 9.95", "min output 9.9"
- **滑点限制**: "slippage < 0.5%", "max slippage 1%"

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
