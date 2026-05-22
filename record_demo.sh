#!/bin/bash
# LI.FI Intents × AI Agent - Demo 录屏脚本
# 使用 ScreenStudio 录制

echo "🎬 LI.FI Intents × AI Agent Demo"
echo "=================================="
echo ""
echo "准备录制..."
echo ""

# 1. 展示 Web UI
echo "1️⃣ 展示 Web UI"
echo "   打开浏览器: http://143.198.95.119:8888"
echo "   展示 Dashboard、Solver Tools、Route Health"
echo ""
read -p "按 Enter 继续..."

# 2. 展示 CLI
echo "2️⃣ 展示 CLI 交互"
echo "   运行: python3 -m lifi_agent"
echo "   测试: send 10 USDC from Base to Arbitrum"
echo "   测试: compare 50 USDC from Base to Polygon"
echo "   测试: route health base"
echo "   测试: stats"
echo ""
read -p "按 Enter 继续..."

# 3. 展示 Demo 脚本
echo "3️⃣ 展示 Demo 脚本"
echo "   运行: python3 demo_script.py"
echo ""
read -p "按 Enter 继续..."

# 4. 展示架构
echo "4️⃣ 展示技术架构"
echo "   展示 SUBMISSION.md 中的架构图"
echo ""
read -p "按 Enter 完成录制"

echo ""
echo "✅ 录制完成！"
echo "视频文件: output/demo_final.mp4"
