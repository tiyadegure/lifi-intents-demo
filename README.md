# LI.FI Intents × AI Agent

一个基于 LI.FI Intents MCP 协议的 AI Agent，用自然语言就能跨链转账。

## ✨ 功能亮点

- 🛡️ **Safe Verdict** - 策略驱动的安全裁决（EXECUTABLE or REFUSED）
- 🔍 **Decision Trace** - 逐步追踪决策过程，展示 MCP 调用细节
- 🔧 **Solver-Aware Checks** - 路由健康、报价可用性、Solver 库存检查
- 🏥 **Doctor 命令** - MCP 连接和配置诊断
- 🤖 **AI 意图解析** - 自然语言 → 跨链操作 + 策略约束
- 🔗 **MCP 协议集成** - 直接调用 LI.FI Intents
- 📊 **Web UI Dashboard** - 报价历史、统计面板、Solver 工具
- 💻 **CLI 交互界面** - 终端操作，开发者友好
- 📦 **Python SDK** - `pip install lifi-agent`
- 🛠️ **Solver Tools** - Route Health、Quote Inventory、Become a Solver

## 📚 文档

- **[PITFALLS.md](PITFALLS.md)** - 10 个 LI.FI Intents MCP 开发陷阱
- **[SUBMISSION.md](SUBMISSION.md)** - 提交材料清单

## 🚀 快速开始

### 安装
```bash
# 克隆仓库
git clone https://github.com/tiyadegure/lifi-intents-demo.git
cd lifi-intents-demo

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -e .
```

### CLI 使用
```bash
# 激活虚拟环境
source .venv/bin/activate

# 运行 CLI
python -m lifi_agent

# Safe Verdict 示例（带决策追踪）
> safe send 10 USDC from Base to Arbitrum if fee < 0.5%
> safe send 10 USDC from Base to Arbitrum if fee < 0.1% and route is healthy
> safe send 10 USDC from Base to Arbitrum avoid Ethereum prefer cheapest route

# Solver-aware checks
> solver base arbitrum USDC USDC
> solver base arbitrum
> solver ethereum polygon

# 普通命令
> send 10 USDC from Base to Arbitrum
> compare 50 USDC from Base to Polygon
> route health base
> stats
```

### Web UI
```bash
# 安装 Web 依赖
pip install -e ".[web]"

# 启动服务
python -m lifi_agent.server
# 打开 http://localhost:8888
```

## 🏗️ 技术架构

```
User (自然语言)
     ↓
AI Agent (意图解析 + LLM)
     ↓
MCP Client (协议封装)
     ↓
LI.FI Intents MCP Server
     ↓
Solver Network (跨链执行)
```

## 📁 项目结构

```
lifi-intents-demo/
├── lifi_agent/
│   ├── __init__.py
│   ├── __main__.py
│   ├── agent.py          # AI Agent + 意图解析
│   ├── mcp_client.py     # MCP 协议客户端
│   └── server.py         # Web UI 后端
├── demo_script.py        # Demo 演示脚本
├── SUBMISSION.md         # 提交材料
├── x_thread.md           # X Thread 文案
└── README.md
```

## 🎯 为什么这个项目重要？

1. **降低门槛** - 不需要懂链、代币、Gas，自然语言就能跨链
2. **AI 原生** - 符合 AI Agent 时代趋势
3. **MCP 标准** - 可以集成到任何 AI 助手（Claude、GPT、Hermes）
4. **Solver 机会** - 展示了 Solver 生态的可能性

## 📺 Demo

- **Web UI**: http://143.198.95.119:8888
- **Demo 视频**: output/demo_v2.mp4
- **GitHub**: https://github.com/tiyadegure/lifi-intents-demo

## 📝 提交材料

- [x] 代码（GitHub）
- [x] Demo 视频
- [x] Web UI 演示
- [x] X Thread 文案
- [ ] 提交表单（5/26 开放）

## 📄 License

MIT
