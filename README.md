# LI.FI Intents × AI Agent Demo

AI Agent 通过 MCP 协议与 LI.FI Intents 跨链意图市场交互的演示项目。

## 项目结构

```
lifi-intents-demo/
├── demo/
│   └── agent_demo.py      # 终端演示脚本（可直接运行）
├── remotion/
│   ├── src/
│   │   ├── Root.tsx        # Remotion 组合定义
│   │   ├── Demo.tsx        # 视频组件（动画 + 布局）
│   │   └── index.ts        # 入口
│   ├── remotion.config.ts  # 配置
│   └── tsconfig.json
├── output/
│   └── demo.mp4            # 渲染好的 30s 演示视频（1080p）
├── x_thread.md             # X Thread 文案
└── README.md
```

## 运行 Demo

```bash
python3 demo/agent_demo.py
```

## 渲染视频

```bash
cd remotion
npx remotion render LifiIntentsDemo --output=../output/demo.mp4 --codec=h264
```

## 技术要点

- **MCP Server**: `https://intents-mcp.li.fi/mcp`（LI.FI 官方托管）
- **协议**: MCP (Model Context Protocol) 2025-03-26
- **工具**: 13 个（6 Integrator + 7 Solver）
- **核心流程**: Intent → MCP → Order Server → Solver → Settlement

## Links

- [LI.FI Intents Docs](https://docs.li.fi/lifi-intents/introduction)
- [MCP Server](https://intents-mcp.li.fi/mcp)
- [Open Intents Framework](https://github.com/OpenIntentsFramework)
