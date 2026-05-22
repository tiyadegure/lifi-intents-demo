#!/usr/bin/env python3
"""
LI.FI Intents × AI Agent - Safe Verdict Demo
演示完整流程：意图解析 → 策略检查 → 安全裁决
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
    print("🛡️  LI.FI Intents × AI Agent — Safe Verdict Demo")
    print("="*70)

def print_verdict(verdict):
    """Print verdict in a beautiful format."""
    if verdict.executable:
        print(f"\n  ✓ Verdict: [bold green]EXECUTABLE[/bold green]")
    else:
        print(f"\n  ✗ Verdict: [bold red]REFUSED[/bold red]")
    
    print("\n  Checks:")
    for check in verdict.checks:
        icon = "✓" if check["passed"] else "✗"
        print(f"    {icon} {check['name']}: {check['detail']}")
    
    print(f"\n  Reason:")
    print(f"    {verdict.reason}")
    
    if verdict.executable and verdict.quote_data:
        quotes = verdict.quote_data.get("quotes", [])
        if quotes:
            q = quotes[0]
            print(f"\n  Quote Details:")
            print(f"    Output: {q.get('outputAmount', 'N/A')}")
            print(f"    Quote ID: {q.get('quoteId', 'N/A')[:16]}...")

async def demo_safe_verdict():
    """演示 Safe Verdict 功能"""
    print_banner()
    
    # 示例 1: 有策略约束的意图
    print("\n📝 示例 1: 带策略约束的意图")
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
    verdict = agent.safe_verdict(intent, policy)
    
    # 显示结果
    print_verdict(verdict)
    
    # 示例 2: 无策略约束的意图
    print("\n\n📝 示例 2: 无策略约束的意图")
    print("-" * 50)
    user_input2 = "send 10 USDC from Base to Arbitrum"
    print(f"用户输入: {user_input2}")
    
    intent2, policy2 = parse_intent_with_policy(user_input2)
    print(f"\n解析结果:")
    print(f"  - Intent: {intent2.amount} {intent2.token.upper()} {intent2.from_chain} → {intent2.to_chain}")
    print(f"  - Policy: {policy2}")
    
    print("\n🔍 执行 Safe Verdict 检查...")
    verdict2 = agent.safe_verdict(intent2, policy2)
    
    print_verdict(verdict2)
    
    # 示例 3: 严格策略（可能被拒绝）
    print("\n\n📝 示例 3: 严格策略（可能被拒绝）")
    print("-" * 50)
    user_input3 = "send 10 USDC from Base to Arbitrum only if fee < 0.1% and route is healthy"
    print(f"用户输入: {user_input3}")
    
    intent3, policy3 = parse_intent_with_policy(user_input3)
    print(f"\n解析结果:")
    print(f"  - Intent: {intent3.amount} {intent3.token.upper()} {intent3.from_chain} → {intent3.to_chain}")
    print(f"  - Policy: {policy3}")
    
    print("\n🔍 执行 Safe Verdict 检查...")
    verdict3 = agent.safe_verdict(intent3, policy3)
    
    print_verdict(verdict3)
    
    # 展示架构
    print("\n\n🏗️  Safe Verdict 架构")
    print("-" * 50)
    print("""
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
    """)
    
    print("\n✨ Demo 完成!")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(demo_safe_verdict())
