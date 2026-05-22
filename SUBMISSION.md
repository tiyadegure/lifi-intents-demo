# LI.FI Intents × AI Agent - 提交材料

## 项目名称
LI.FI Intents × AI Agent: 自然语言跨链交互

## 一句话描述
用自然语言就能跨链转账的 AI Agent，基于 LI.FI Intents MCP 协议

## 项目亮点
1. **AI 意图解析** - 自然语言 → 跨链操作
2. **MCP 协议集成** - 直接调用 LI.FI Intents
3. **完整工具链** - Web UI + CLI + SDK
4. **Solver 生态** - Route Health、Quote Inventory、Become a Solver

## 技术架构
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

## 功能列表
- ✅ 自然语言意图解析（"send 10 USDC from Base to Arbitrum"）
- ✅ MCP 协议集成（LI.FI Intents）
- ✅ Web UI Dashboard（报价历史、统计面板）
- ✅ Solver Tools（Route Health、Quote Inventory、Become a Solver）
- ✅ CLI 交互界面
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
