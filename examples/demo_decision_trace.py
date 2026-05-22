#!/usr/bin/env python3
"""
LI.FI Intents × AI Agent - Decision Trace Demo
演示完整的决策追踪功能
"""

import asyncio
import json
import time
from lifi_agent.mcp_client import MCPClient
from lifi_agent.agent import LifAgent, Intent, Policy, parse_intent_with_policy, amount_to_raw

# Demo address (Vitalik's address for demo purposes)
DEMO_ADDRESS = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"

def print_banner():
    print("\n" + "="*70)
    print("🔍 LI.FI Intents × AI Agent — Decision Trace Demo")
    print("="*70)

def print_decision_trace(result):
    """Print decision trace in a beautiful format."""
    # Verdict
    if result.verdict == "EXECUTABLE":
        print(f"\n  ✓ Verdict: EXECUTABLE")
    else:
        print(f"\n  ✗ Verdict: REFUSED")
    
    # Decision trace
    print(f"\n  Decision Trace:")
    for i, step in enumerate(result.steps, 1):
        # Status icon
        if step.status == "passed":
            icon = "✓"
        elif step.status == "failed":
            icon = "✗"
        elif step.status == "warning":
            icon = "⚠"
        else:  # skipped
            icon = "○"
        
        # Duration
        duration_str = f" ({step.duration_ms}ms)" if step.duration_ms > 0 else ""
        
        # MCP tool info
        mcp_str = ""
        if step.mcp_tool:
            mcp_str = f" via {step.mcp_tool}"
        
        print(f"    {icon} {step.name}: {step.detail}{duration_str}{mcp_str}")
    
    # Reason
    print(f"\n  Reason:")
    print(f"    {result.reason}")
    
    # Timing
    print(f"\n  Total duration: {result.total_duration_ms}ms")
    
    # Quote details
    if result.verdict == "EXECUTABLE" and result.quote_data:
        quotes = result.quote_data.get("quotes", [])
        if quotes:
            q = quotes[0]
            print(f"\n  Quote Details:")
            print(f"    Output: {q.get('outputAmount', 'N/A')}")
            print(f"    Quote ID: {q.get('quoteId', 'N/A')[:16]}...")

async def demo_decision_trace():
    """演示决策追踪功能"""
    print_banner()
    
    # 示例 1: 基础策略
    print("\n📝 示例 1: 基础策略（费用限制）")
    print("-" * 50)
    user_input = "send 10 USDC from Base to Arbitrum only if fee < 0.5%"
    print(f"用户输入: {user_input}")
    
    # 解析意图和策略
    intent, policy = parse_intent_with_policy(user_input)
    print(f"\n解析结果:")
    print(f"  - Intent: {intent.amount} {intent.token.upper()} {intent.from_chain} → {intent.to_chain}")
    print(f"  - Policy: {policy}")
    
    # 创建 Agent 并执行 Safe Verdict
    agent = LifAgent()
    
    print("\n🔍 执行 Safe Verdict 检查...")
    result = agent.safe_verdict_trace(intent, policy)
    
    # 显示结果
    print_decision_trace(result)
    
    # 示例 2: 组合策略
    print("\n\n📝 示例 2: 组合策略（费用 + 健康 + 避免链）")
    print("-" * 50)
    user_input = "send 10 USDC from Base to Arbitrum only if fee < 0.5% and route is healthy avoid Ethereum"
    print(f"用户输入: {user_input}")
    
    intent, policy = parse_intent_with_policy(user_input)
    print(f"\n解析结果:")
    print(f"  - Intent: {intent.amount} {intent.token.upper()} {intent.from_chain} → {intent.to_chain}")
    print(f"  - Policy: {policy}")
    
    print("\n🔍 执行 Safe Verdict 检查...")
    result = agent.safe_verdict_trace(intent, policy)
    
    print_decision_trace(result)
    
    # 示例 3: 严格策略（可能被拒绝）
    print("\n\n📝 示例 3: 严格策略（可能被拒绝）")
    print("-" * 50)
    user_input = "send 10 USDC from Base to Arbitrum only if fee < 0.1% and route is healthy"
    print(f"用户输入: {user_input}")
    
    intent, policy = parse_intent_with_policy(user_input)
    print(f"\n解析结果:")
    print(f"  - Intent: {intent.amount} {intent.token.upper()} {intent.from_chain} → {intent.to_chain}")
    print(f"  - Policy: {policy}")
    
    print("\n🔍 执行 Safe Verdict 检查...")
    result = agent.safe_verdict_trace(intent, policy)
    
    print_decision_trace(result)
    
    # 展示架构
    print("\n\n🏗️  Decision Trace 架构")
    print("-" * 50)
    print("""
    User Input (自然语言 + 策略)
         ↓
    Parse Intent + Policy
         ↓
    ┌─────────────────────────────────────┐
    │  Safe Verdict Pipeline              │
    │  ┌─────────────────────────────────┐│
    │  │ 1. Parse Intent                 ││
    │  │ 2. Parse Policy                 ││
    │  │ 3. Check Supported Route        ││
    │  │ 4. Check Route Health (if req)  ││
    │  │ 5. Get Quote                    ││
    │  │ 6. Calculate Fee                ││
    │  │ 7. Check Policy Constraints     ││
    │  │ 8. Final Verdict                ││
    │  └─────────────────────────────────┘│
    │                                     │
    │  Decision Trace                     │
    │  ┌─────────────────────────────────┐│
    │  │ Each step has:                  ││
    │  │ - name                          ││
    │  │ - status (passed/failed/skipped)││
    │  │ - detail                        ││
    │  │ - duration_ms                   ││
    │  │ - mcp_tool                      ││
    │  │ - mcp_args                      ││
    │  │ - mcp_result                    ││
    │  └─────────────────────────────────┘│
    └─────────────────────────────────────┘
    """)
    
    print("\n✨ Demo 完成!")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(demo_decision_trace())
