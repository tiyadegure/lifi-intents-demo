import {
  AbsoluteFill,
  Sequence,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  staticFile,
} from "remotion";

// ── Title Sequence ──
const TitleCard = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = interpolate(frame, [0, 30], [0, 1], { extrapolateRight: "clamp" });
  const y = spring({ frame, fps, config: { damping: 12 } });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0a0a0a",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <div
        style={{
          opacity,
          transform: `translateY(${interpolate(y, [0, 1], [50, 0])}px)`,
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontSize: 72,
            fontWeight: 800,
            color: "#ffffff",
            fontFamily: "Inter, system-ui, sans-serif",
            marginBottom: 16,
          }}
        >
          LI.FI Intents × AI Agent
        </div>
        <div
          style={{
            fontSize: 32,
            color: "#888",
            fontFamily: "Inter, system-ui, sans-serif",
          }}
        >
          Cross-Chain via MCP — Powered by Hermes Agent
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ── Caption Overlay ──
const Caption = ({ text, startFrame, duration = 90 }) => {
  const frame = useCurrentFrame();
  const relFrame = frame - startFrame;

  if (relFrame < 0 || relFrame > duration) return null;

  const opacity = interpolate(
    relFrame,
    [0, 15, duration - 15, duration],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <div
      style={{
        position: "absolute",
        bottom: 80,
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        opacity,
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(0, 0, 0, 0.85)",
          borderRadius: 12,
          padding: "16px 32px",
          maxWidth: 1200,
        }}
      >
        <div
          style={{
            fontSize: 28,
            color: "#ffffff",
            fontFamily: "Inter, system-ui, sans-serif",
            lineHeight: 1.5,
            textAlign: "center",
          }}
        >
          {text}
        </div>
      </div>
    </div>
  );
};

// ── Terminal Recording Placeholder ──
const TerminalBackground = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#1a1a2e",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      {/* Replace with actual terminal recording */}
      <div
        style={{
          width: 1600,
          height: 900,
          backgroundColor: "#0d1117",
          borderRadius: 16,
          border: "2px solid #333",
          overflow: "hidden",
          padding: 32,
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 22,
          color: "#c9d1d9",
          lineHeight: 1.6,
        }}
      >
        <div style={{ color: "#58a6ff" }}>$ python3 mcp_demo.py</div>
        <div style={{ marginTop: 16, color: "#7ee787" }}>
          ════════════════════════════════════════
        </div>
        <div style={{ color: "#f0f6fc", fontWeight: 700, fontSize: 28 }}>
          LI.FI Intents × AI Agent Demo
        </div>
        <div style={{ color: "#7ee787" }}>
          ════════════════════════════════════════
        </div>
        <div style={{ marginTop: 24, color: "#79c0ff" }}>
          🤖 Agent: Connecting to LI.FI Intents MCP Server...
        </div>
        <div style={{ marginTop: 8, color: "#d2a8ff" }}>
          ⚡ Calling MCP Tool: initialize
        </div>
        <div style={{ color: "#7ee787" }}>✅ Connected!</div>
      </div>
    </AbsoluteFill>
  );
};

// ── Outro ──
const OutroCard = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 30], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0a0a0a",
        justifyContent: "center",
        alignItems: "center",
        opacity,
      }}
    >
      <div style={{ textAlign: "center" }}>
        <div
          style={{
            fontSize: 64,
            fontWeight: 800,
            color: "#ffffff",
            fontFamily: "Inter, system-ui, sans-serif",
            marginBottom: 24,
          }}
        >
          AI Agents × Cross-Chain 🚀
        </div>
        <div
          style={{
            fontSize: 28,
            color: "#888",
            fontFamily: "Inter, system-ui, sans-serif",
          }}
        >
          docs.li.fi/lifi-intents
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ── Main Composition ──
export const DemoVideo: React.FC = () => {
  return (
    <AbsoluteFill>
      {/* Title: 0-3s */}
      <Sequence from={0} durationInFrames={90}>
        <TitleCard />
      </Sequence>

      {/* Terminal Demo: 3-50s */}
      <Sequence from={90} durationInFrames={1200}>
        <TerminalBackground />
        <Caption
          text="AI Agent connects to LI.FI Intents via MCP Protocol"
          startFrame={30}
          duration={120}
        />
        <Caption
          text="Requesting cross-chain quote: 10 USDC Base → Arbitrum"
          startFrame={200}
          duration={120}
        />
        <Caption
          text="Solvers compete with standing quotes — best price wins"
          startFrame={380}
          duration={120}
        />
        <Caption
          text="Intent matched! Solver delivers instantly on destination chain"
          startFrame={560}
          duration={120}
        />
        <Caption
          text="No bridge selection, no path optimization — just express intent"
          startFrame={740}
          duration={120}
        />
      </Sequence>

      {/* Outro: 50-60s */}
      <Sequence from={1500} durationInFrames={300}>
        <OutroCard />
      </Sequence>
    </AbsoluteFill>
  );
};
