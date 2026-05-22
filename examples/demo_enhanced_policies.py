#!/usr/bin/env python3
"""
LI.FI Intents × AI Agent - Enhanced Policy Parser Demo
演示增强的策略解析功能
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
    print("🛡️  LI.FI Intents × AI Agent — Enhanced Policy Parser Demo")
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

def print_policy(policy):
    """Print policy details."""
    print(f"  Policy: {policy}")
    if policy.max_fee_pct is not None:
        print(f"    - Max Fee: {policy.max_fee_pct}%")
    if policy.require_healthy_route:
        print(f"    - Require Healthy Route: Yes")
    if policy.min_output_amount is not None:
        print(f"    - Min Output: {policy.min_output_amount}")
    if policy.max_slippage is not None:
        print(f"    - Max Slippage: {policy.max_slippage}%")
    if not policy.allow_cross_chain:
        print(f"    - Allow Cross-Chain: No")
    if policy.avoid_chains:
        print(f"    - Avoid Chains: {', '.join(policy.avoid_chains)}")
    if policy.prefer_cheapest:
        print(f"    - Prefer Cheapest: Yes")
    if not policy.require_quote:
        print(f"    - Require Quote: No")

async def demo_enhanced_policies():
    """演示增强的策略解析功能"""
    print_banner()
    
    # 示例 1: 基础策略
    print("\n📝 示例 1: 基础策略（费用限制）")
    print("-" * 50)
    user_input = "send 10 USDC from Base to Arbitrum only if fee < 0.5%"
    print(f"用户输入: {user_input}")
    
    intent, policy = parse_intent_with_policy(user_input)
    print(f"\n解析结果:")
    print(f"  - Intent: {intent.amount} {intent.token.upper()} {intent.from_chain} → {intent.to_chain}")
    print_policy(policy)
    
    # 示例 2: 避免特定链
    print("\n\n📝 示例 2: 避免特定链")
    print("-" * 50)
    user_input = "send 10 USDC from Base to Arbitrum avoid Ethereum"
    print(f"用户输入: {user_input}")
    
    intent, policy = parse_intent_with_policy(user_input)
    print(f"\n解析结果:")
    print(f"  - Intent: {intent.amount} {intent.token.upper()} {intent.from_chain} → {intent.to_chain}")
    print_policy(policy)
    
    # 示例 3: 偏好最便宜路线
    print("\n\n📝 示例 3: 偏好最便宜路线")
    print("-" * 50)
    user_input = "send 10 USDC from Base to Arbitrum prefer cheapest route"
    print(f"用户输入: {user_input}")
    
    intent, policy = parse_intent_with_policy(user_input)
    print(f"\n解析结果:")
    print(f"  - Intent: {intent.amount} {intent.token.upper()} {intent.from_chain} → {intent.to_chain}")
    print_policy(policy)
    
    # 示例 4: 无报价时拒绝执行
    print("\n\n📝 示例 4: 无报价时拒绝执行")
    print("-" * 50)
    user_input = "send 10 USDC from Base to Arbitrum do not execute if no quote"
    print(f"用户输入: {user_input}")
    
    intent, policy = parse_intent_with_policy(user_input)
    print(f"\n解析结果:")
    print(f"  - Intent: {intent.amount} {intent.token.upper()} {intent.from_chain} → {intent.to_chain}")
    print_policy(policy)
    
    # 示例 5: 组合策略
    print("\n\n📝 示例 5: 组合策略")
    print("-" * 50)
    user_input = "send 10 USDC from Base to Arbitrum only if fee < 0.5% and route is healthy avoid Ethereum prefer cheapest route"
    print(f"用户输入: {user_input}")
    
    intent, policy = parse_intent_with_policy(user_input)
    print(f"\n解析结果:")
    print(f"  - Intent: {intent.amount} {intent.token.upper()} {intent.from_chain} → {intent.to_chain}")
    print_policy(policy)
    
    # 示例 6: 执行 Safe Verdict
    print("\n\n📝 示例 6: 执行 Safe Verdict（组合策略）")
    print("-" * 50)
    user_input = "send 10 USDC from Base to Arbitrum only if fee < 0.5% avoid Ethereum"
    print(f"用户输入: {user_input}")
    
    intent, policy = parse_intent_with_policy(user_input)
    print(f"\n解析结果:")
    print(f"  - Intent: {intent.amount} {intent.token.upper()} {intent.from_chain} → {intent.to_chain}")
    print_policy(policy)
    
    # 创建 Agent 并执行 Safe Verdict
    agent = LifAgent()
    
    print("\n🔍 执行 Safe Verdict 检查...")
    verdict = agent.safe_verdict(intent, policy)
    
    # 显示结果
    print_verdict(verdict)
    
    # 展示支持的自然语言模式
    print("\n\n📚 支持的自然语言模式")
    print("-" * 50)
    print("""
    费用限制:
      - "only if fee < 0.5%"
      - "fee under 1%"
      - "max fee 0.3%"
    
    路由健康:
      - "only if route is healthy"
      - "healthy route"
    
    避免链:
      - "avoid Ethereum"
      - "avoid eth and polygon"
    
    偏好:
      - "prefer cheapest route"
      - "cheapest route"
    
    报价要求:
      - "do not execute if no quote"
      - "no quote = no execute"
    
    跨链限制:
      - "same chain only"
      - "no cross-chain"
    
    输出限制:
      - "output >= 9.95"
      - "min output 9.9"
    
    滑点限制:
      - "slippage < 0.5%"
      - "max slippage 1%"
    """)
    
    print("\n✨ Demo 完成!")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(demo_enhanced_policies())
