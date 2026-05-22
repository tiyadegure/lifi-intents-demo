#!/usr/bin/env python3
"""
LI.FI Intents × AI Agent - Doctor Command Demo
演示 doctor 命令的诊断功能
"""

import asyncio
import json
import time
from lifi_agent.mcp_client import MCPClient
from lifi_agent.agent import LifAgent

def print_banner():
    print("\n" + "="*70)
    print("🏥 LI.FI Intents × AI Agent — Doctor Command Demo")
    print("="*70)

def print_doctor_report(report):
    """Print doctor report."""
    print("\n  LI.FI Intents MCP Doctor\n")
    
    # Display checks
    for check in report["checks"]:
        icon = "✓" if check["passed"] else "✗"
        print(f"  {icon} {check['name']}: {check['detail']}")
    
    # Display warnings
    if report["warnings"]:
        print(f"\n  Warnings:")
        for warning in report["warnings"]:
            print(f"  ! {warning['name']}: {warning['detail']}")

async def demo_doctor():
    """演示 doctor 命令功能"""
    print_banner()
    
    # 创建 Agent
    agent = LifAgent()
    
    # 运行 doctor 检查
    print("\n📝 运行 doctor 检查...")
    print("-" * 50)
    
    report = agent.doctor()
    print_doctor_report(report)
    
    # 展示架构
    print("\n\n🏗️  Doctor 命令架构")
    print("-" * 50)
    print("""
    User Command: doctor
         ↓
    ┌─────────────────────────────────────┐
    │  Doctor Checks                      │
    │  ┌─────────────────────────────────┐│
    │  │ 1. MCP endpoint reachable       ││
    │  │ 2. MCP session initialized      ││
    │  │ 3. get-supported-routes works   ││
    │  │ 4. Base USDC address configured ││
    │  │ 5. Arbitrum USDC address config ││
    │  │ 6. route health tool reachable  ││
    │  │ 7. request-quote works          ││
    │  └─────────────────────────────────┘│
    │                                     │
    │  Warnings                           │
    │  ┌─────────────────────────────────┐│
    │  │ - OPENAI_API_KEY not set        ││
    │  │ - Amount unit behavior          ││
    │  └─────────────────────────────────┘│
    └─────────────────────────────────────┘
    """)
    
    print("\n✨ Demo 完成!")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(demo_doctor())
