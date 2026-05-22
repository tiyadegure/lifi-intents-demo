#!/usr/bin/env python3
"""
LI.FI Intents × AI Agent - Solver-Aware Checks Demo
演示 Solver 工具模块
"""

import asyncio
import json
import time
from lifi_agent.mcp_client import MCPClient
from lifi_agent.agent import LifAgent

def print_banner():
    print("\n" + "="*70)
    print("🔧 LI.FI Intents × AI Agent — Solver-Aware Checks Demo")
    print("="*70)

def print_solver_report(report):
    """Print solver-aware checks report."""
    print(f"\n  Route: {report['route']}")
    print()
    
    # Display checks
    print("  Checks:")
    for check in report["checks"]:
        # Status icon
        if check["passed"]:
            icon = "✓"
        elif check["status"] == "skipped":
            icon = "○"
        else:
            icon = "✗"
        
        # Status text
        status_text = check["status"].upper()
        if check["status"] == "healthy":
            status_text = "HEALTHY"
        elif check["status"] == "active":
            status_text = "ACTIVE"
        elif check["status"] == "available":
            status_text = "AVAILABLE"
        elif check["status"] == "empty":
            status_text = "EMPTY"
        elif check["status"] == "unavailable":
            status_text = "UNAVAILABLE"
        elif check["status"] == "error":
            status_text = "ERROR"
        
        print(f"    {icon} {check['name']}: {status_text}")
        
        # Show details for failed checks
        if not check["passed"] and check["status"] != "skipped":
            details = check.get("details", {})
            if isinstance(details, dict):
                for key, value in details.items():
                    if key != "routes":  # Skip routes to avoid clutter
                        print(f"      {key}: {value}")
            else:
                print(f"      {details}")
    
    # Summary
    summary = report["summary"]
    print(f"\n  Summary:")
    print(f"    Total checks: {summary['total_checks']}")
    print(f"    Passed: {summary['passed_checks']}")
    print(f"    Failed: {summary['failed_checks']}")
    print(f"    Overall: {summary['overall_status'].upper()}")

async def demo_solver_checks():
    """演示 Solver-aware checks 功能"""
    print_banner()
    
    # 创建 Agent
    agent = LifAgent()
    
    # 示例 1: 基础路由检查
    print("\n📝 示例 1: 基础路由检查（Base → Arbitrum）")
    print("-" * 50)
    print("命令: solver base arbitrum")
    
    report = agent.solver_aware_checks("base", "arbitrum")
    print_solver_report(report)
    
    # 示例 2: 带资产的路由检查
    print("\n\n📝 示例 2: 带资产的路由检查（Base → Arbitrum, USDC → USDC）")
    print("-" * 50)
    print("命令: solver base arbitrum USDC USDC")
    
    report = agent.solver_aware_checks("base", "arbitrum", "USDC", "USDC")
    print_solver_report(report)
    
    # 示例 3: 其他路由
    print("\n\n📝 示例 3: 其他路由（Ethereum → Polygon）")
    print("-" * 50)
    print("命令: solver ethereum polygon")
    
    report = agent.solver_aware_checks("ethereum", "polygon")
    print_solver_report(report)
    
    # 展示架构
    print("\n\n🏗️  Solver-Aware Checks 架构")
    print("-" * 50)
    print("""
    User Command: solver <from_chain> <to_chain> [from_asset] [to_asset]
         ↓
    ┌─────────────────────────────────────┐
    │  Solver-Aware Checks                │
    │  ┌─────────────────────────────────┐│
    │  │ 1. Route Health                 ││
    │  │    - check-route-health MCP     ││
    │  │    - Status: healthy/degraded   ││
    │  │                                 ││
    │  │ 2. Quote Availability           ││
    │  │    - get-supported-routes MCP   ││
    │  │    - Check if route exists      ││
    │  │                                 ││
    │  │ 3. Solver Inventory             ││
    │  │    - get-quote-inventory MCP    ││
    │  │    - Active quotes count        ││
    │  └─────────────────────────────────┘│
    │                                     │
    │  Summary                            │
    │  ┌─────────────────────────────────┐│
    │  │ - Total checks                  ││
    │  │ - Passed/Failed counts          ││
    │  │ - Overall status                ││
    │  └─────────────────────────────────┘│
    └─────────────────────────────────────┘
    """)
    
    print("\n✨ Demo 完成!")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(demo_solver_checks())
