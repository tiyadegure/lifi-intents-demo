import {
  AbsoluteFill,
  Sequence,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  staticFile,
  Audio,
} from "remotion";
import {
  Particles,
  TypewriterText,
  AnimatedProgress,
  AnimatedCounter,
  GlowText,
} from "./components";
import { AudioMix } from "./AudioMix";

// ── Title Sequence (with particles + spring) ──
const TitleCard = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const s = spring({ frame, fps, config: { damping: 12, stiffness: 150 } });
  const scale = interpolate(s, [0, 1], [0.8, 1]);
  const opacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0d1117",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <Particles count={50} color="#4C64FF" speed={0.25} />
      <div
        style={{
          opacity,
          transform: `scale(${scale})`,
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontSize: 64,
            fontWeight: 800,
            fontFamily: "'JetBrains Mono', monospace",
            marginBottom: 16,
          }}
        >
          <GlowText color="#4C64FF" glowColor="#4C64FF">
            🛡️ LI.FI Intents
          </GlowText>
        </div>
        <div
          style={{
            fontSize: 28,
            color: "#8b949e",
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          Developer Playground
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ── Terminal Demo Scene (with typewriter) ──
const TerminalDemo = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0d1117",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <div
        style={{
          width: 1500,
          backgroundColor: "#161b22",
          borderRadius: 16,
          border: "1px solid #30363d",
          overflow: "hidden",
          padding: 32,
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 20,
          color: "#e6edf3",
          lineHeight: 1.7,
          boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
        }}
      >
        {/* Window dots */}
        <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
          <div style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: "#ff5f56" }} />
          <div style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: "#ffbd2e" }} />
          <div style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: "#27c93f" }} />
        </div>

        {/* Typewriter content */}
        <div style={{ color: "#8b949e" }}>
          $ python3 -m lifi_agent
        </div>
        <div style={{ marginTop: 8, color: "#39d353", fontWeight: 600 }}>
          ❯ send 0.001 WETH from Base to Arbitrum
        </div>
        <div style={{ marginTop: 16, color: "#bc8cff", fontWeight: 600 }}>
          🤖 Agent:
        </div>
        <div style={{ color: "#8b949e", marginTop: 4 }}>
          Analyzing intent...
        </div>

        {/* Progress bar — route analysis */}
        <div style={{ marginTop: 20, width: "80%" }}>
          <AnimatedProgress
            from={0}
            to={1}
            durationFrames={90}
            label="Route Analysis"
            delay={30}
            color="#4C64FF"
          />
        </div>

        <div style={{ marginTop: 16, color: "#d29922", fontWeight: 600 }}>
          ⚡ MCP → request-quote
        </div>
        <div style={{ marginTop: 8, color: "#3fb950", fontWeight: 600 }}>
          ✅ Verdict: EXECUTABLE
        </div>
        <div style={{ color: "#8b949e", marginTop: 4 }}>
          Output:{" "}
          <AnimatedCounter
            from={0}
            to={2.481}
            durationFrames={60}
            suffix=" USDC"
            decimals={3}
            delay={100}
            style={{ color: "#3fb950", fontWeight: 600 }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ── Outro (with particles) ──
const OutroCard = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 30], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0d1117",
        justifyContent: "center",
        alignItems: "center",
        opacity,
      }}
    >
      <Particles count={60} color="#4C64FF" speed={0.3} />
      <div style={{ textAlign: "center" }}>
        <div
          style={{
            fontSize: 56,
            fontWeight: 800,
            fontFamily: "'JetBrains Mono', monospace",
            marginBottom: 24,
          }}
        >
          <GlowText color="#4C64FF">
            AI Agents × Cross-Chain 🚀
          </GlowText>
        </div>
        <div
          style={{
            fontSize: 22,
            color: "#8b949e",
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          docs.li.fi/lifi-intents · lifi.degure.me
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ── Main Composition ──
export const DemoVideo: React.FC = () => {
  return (
    <AbsoluteFill>
      <AudioMix />

      {/* Title: 0-3s */}
      <Sequence from={0} durationInFrames={90}>
        <TitleCard />
      </Sequence>

      {/* Terminal Demo: 3-50s */}
      <Sequence from={90} durationInFrames={1200}>
        <TerminalDemo />
      </Sequence>

      {/* Outro: 50-60s */}
      <Sequence from={1290} durationInFrames={300}>
        <OutroCard />
      </Sequence>
    </AbsoluteFill>
  );
};
