import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Sequence,
  Audio,
  staticFile,
} from "remotion";

const C = {
  bg: "#0d1117",
  card: "#161b22",
  border: "#30363d",
  text: "#e6edf3",
  dim: "#8b949e",
  blue: "#58a6ff",
  green: "#3fb950",
  yellow: "#d29922",
  purple: "#bc8cff",
  cyan: "#39d353",
};

// ── Reusable components ──────────────────────────────────────────────
const FadeIn: React.FC<{ children: React.ReactNode; delay?: number; duration?: number }> = ({
  children,
  delay = 0,
  duration = 20,
}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame - delay, [0, duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const y = interpolate(frame - delay, [0, duration], [20, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div style={{ opacity, transform: `translateY(${y}px)` }}>{children}</div>
  );
};

const Terminal: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    style={{
      backgroundColor: C.card,
      border: `1px solid ${C.border}`,
      borderRadius: 12,
      padding: 32,
      margin: "0 160px",
      minHeight: 400,
    }}
  >
    <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
      <div style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: "#ff5f56" }} />
      <div style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: "#ffbd2e" }} />
      <div style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: "#27c93f" }} />
    </div>
    {children}
  </div>
);

const Line: React.FC<{
  text: string;
  color?: string;
  delay?: number;
  bold?: boolean;
  size?: number;
}> = ({ text, color = C.text, delay = 0, bold = false, size = 22 }) => {
  const frame = useCurrentFrame();
  if (frame - delay < 0) return null;
  const opacity = interpolate(frame - delay, [0, 8], [0, 1], {
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        fontSize: size,
        color,
        opacity,
        fontWeight: bold ? 700 : 400,
        lineHeight: 1.7,
        whiteSpace: "pre",
      }}
    >
      {text}
    </div>
  );
};

const Box: React.FC<{ title: string; lines: string[]; color?: string; delay?: number }> = ({
  title,
  lines,
  color = C.green,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  if (frame - delay < 0) return null;
  const opacity = interpolate(frame - delay, [0, 15], [0, 1], {
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        opacity,
        margin: "16px 0",
        padding: "16px 24px",
        backgroundColor: C.card,
        border: `1px solid ${C.border}`,
        borderRadius: 8,
      }}
    >
      <div style={{ color, fontWeight: 700, fontSize: 20, marginBottom: 8, fontFamily: "monospace" }}>
        ✓ {title}
      </div>
      {lines.map((l, i) => (
        <div key={i} style={{ color: C.dim, fontSize: 18, fontFamily: "monospace", lineHeight: 1.6 }}>
          {l}
        </div>
      ))}
    </div>
  );
};

const StepCard: React.FC<{
  icon: string;
  title: string;
  desc: string;
  delay: number;
}> = ({ icon, title, desc, delay }) => {
  const frame = useCurrentFrame();
  if (frame - delay < 0) return null;
  const opacity = interpolate(frame - delay, [0, 15], [0, 1], { extrapolateRight: "clamp" });
  const x = interpolate(frame - delay, [0, 15], [30, 0], { extrapolateRight: "clamp" });
  return (
    <div style={{ opacity, transform: `translateX(${x}px)`, marginBottom: 20, display: "flex", gap: 16 }}>
      <div style={{ fontSize: 32 }}>{icon}</div>
      <div>
        <div style={{ fontSize: 22, fontWeight: 700, color: C.text, fontFamily: "monospace" }}>{title}</div>
        <div style={{ fontSize: 17, color: C.dim, fontFamily: "monospace", marginTop: 4 }}>{desc}</div>
      </div>
    </div>
  );
};

// ── Scenes ───────────────────────────────────────────────────────────

const IntroScene: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: C.bg, justifyContent: "center", alignItems: "center" }}>
    <FadeIn delay={5}>
      <div style={{ fontSize: 64, fontWeight: 800, color: C.blue, fontFamily: "monospace", textAlign: "center" }}>
        LI.FI Intents × AI Agent
      </div>
    </FadeIn>
    <FadeIn delay={30}>
      <div style={{ fontSize: 26, color: C.dim, fontFamily: "monospace", marginTop: 16, textAlign: "center" }}>
        Powered by MCP Protocol
      </div>
    </FadeIn>
    <FadeIn delay={60}>
      <div style={{ fontSize: 18, color: C.dim, fontFamily: "monospace", marginTop: 40, textAlign: "center" }}>
        docs.li.fi/lifi-intents · intents-mcp.li.fi/mcp
      </div>
    </FadeIn>
  </AbsoluteFill>
);

const QuestionScene: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: C.bg, justifyContent: "center", alignItems: "center" }}>
    <Terminal>
      <Line text="$ hermes" color={C.dim} delay={0} />
      <Line text="" delay={5} />
      <Line text="Builder:" color={C.cyan} delay={10} bold />
      <Line text="I want to send 10 USDC from Base to Arbitrum." delay={20} />
      <Line text="What's the best rate I can get?" delay={40} />
      <Line text="" delay={55} />
      <Line text="Hermes:" color={C.purple} delay={60} bold />
      <Line text="Let me query the LI.FI Intents solver network." delay={75} />
    </Terminal>
  </AbsoluteFill>
);

const ConnectingScene: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: C.bg, justifyContent: "center", alignItems: "center" }}>
    <FadeIn delay={0}>
      <div style={{ fontSize: 28, color: C.dim, fontFamily: "monospace", textAlign: "center", marginBottom: 40 }}>
        Connecting to LI.FI Intents MCP Server...
      </div>
    </FadeIn>
    <FadeIn delay={30}>
      <Box
        title="MCP Server Connected"
        lines={[
          "Server: lifi-intents v1.0.0",
          "Protocol: MCP (Model Context Protocol)",
          "Tools: 13 available (6 integrator + 7 solver)",
          "Status: Ready",
        ]}
        color={C.blue}
      />
    </FadeIn>
  </AbsoluteFill>
);

const RoutesScene: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: C.bg, justifyContent: "center", alignItems: "center" }}>
    <Terminal>
      <Line text="⚡ MCP → get-supported-routes" color={C.yellow} delay={0} bold />
      <Line text="{}" color={C.dim} delay={10} />
      <Line text="" delay={20} />
      <Line text="✓ 812+ active routes across 15+ chains" color={C.green} delay={30} bold />
      <Line text="  Base, Arbitrum, Ethereum, Optimism," color={C.dim} delay={45} />
      <Line text="  Polygon, BSC, Solana, Tron, Soneium..." color={C.dim} delay={55} />
      <Line text="" delay={70} />
      <Line text="⚡ MCP → request-quote" color={C.yellow} delay={80} bold />
      <Line text="  { fromChain: Base, toChain: Arbitrum," color={C.dim} delay={95} />
      <Line text="    fromToken: USDC, amount: 10 }" color={C.dim} delay={105} />
    </Terminal>
  </AbsoluteFill>
);

const QuoteScene: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: C.bg, justifyContent: "center", alignItems: "center" }}>
    <Terminal>
      <Line text="⚡ MCP → request-quote" color={C.yellow} delay={0} bold />
      <Line text="" delay={5} />
      <Line text="✓ Quote from Solver" color={C.green} delay={15} bold />
      <Line text="" delay={20} />
      <Line text="  Route:    Base → Arbitrum (cross-chain)" delay={25} />
      <Line text="  Input:    10 USDC" delay={35} />
      <Line text="  Output:   9.983725 USDC" color={C.green} delay={45} />
      <Line text="  Fee:      ~0.016 USDC (0.16%)" color={C.dim} delay={55} />
      <Line text="  Type:     exact-input" color={C.dim} delay={65} />
      <Line text="  Solver:   Filled from solver inventory" color={C.dim} delay={75} />
    </Terminal>
  </AbsoluteFill>
);

const ExplainScene: React.FC = () => (
  <AbsoluteFill
    style={{ justifyContent: "center", alignItems: "center", padding: "0 160px" }}
  >
    <div style={{ width: "100%", maxWidth: 1200 }}>
      <FadeIn delay={0}>
        <div style={{ fontSize: 36, fontWeight: 800, color: C.blue, fontFamily: "monospace", marginBottom: 32, textAlign: "center" }}>
          How LI.FI Intents Works
        </div>
      </FadeIn>
      <StepCard icon="1️⃣" title="Intent" desc={'You say WHAT you want: "Send 10 USDC Base→Arbitrum"'} delay={20} />
      <StepCard icon="2️⃣" title="Match" desc="Order server matches against solver standing quotes" delay={60} />
      <StepCard icon="3️⃣" title="Solve" desc="Best solver fills with their own capital — instant delivery" delay={100} />
      <StepCard icon="4️⃣" title="Settle" desc="On-chain verification. Solver reimbursed. You never wait." delay={140} />
      <FadeIn delay={180}>
        <div
          style={{
            marginTop: 24,
            padding: "14px 24px",
            backgroundColor: C.card,
            border: `1px solid ${C.border}`,
            borderRadius: 8,
            fontFamily: "monospace",
            fontSize: 16,
            color: C.dim,
            textAlign: "center",
          }}
        >
          User Intent → MCP Server → Order Server → Solver Network → Delivery
        </div>
      </FadeIn>
    </div>
  </AbsoluteFill>
);

const McpScene: React.FC = () => (
  <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", padding: "0 160px" }}>
    <div style={{ width: "100%", maxWidth: 1200 }}>
      <FadeIn delay={0}>
        <div style={{ fontSize: 32, fontWeight: 700, color: C.text, fontFamily: "monospace", marginBottom: 24, textAlign: "center" }}>
          The magic: all through MCP
        </div>
      </FadeIn>
      <FadeIn delay={20}>
        <div style={{ fontSize: 20, color: C.dim, fontFamily: "monospace", textAlign: "center", marginBottom: 32 }}>
          Any AI agent with MCP support can do this autonomously.
          <br />
          No browser, no UI, no manual steps.
        </div>
      </FadeIn>
      <FadeIn delay={50}>
        <div style={{ display: "flex", gap: 16, justifyContent: "center", marginBottom: 32 }}>
          {[
            { name: "get-supported-routes", desc: "Discover chains" },
            { name: "request-quote", desc: "Get pricing" },
            { name: "prepare-order", desc: "Build order" },
            { name: "track-order", desc: "Monitor status" },
          ].map((t, i) => (
            <div
              key={i}
              style={{
                padding: "12px 16px",
                backgroundColor: C.card,
                border: `1px solid ${C.border}`,
                borderRadius: 8,
                fontFamily: "monospace",
                textAlign: "center",
              }}
            >
              <div style={{ color: C.cyan, fontSize: 16, fontWeight: 600 }}>{t.name}</div>
              <div style={{ color: C.dim, fontSize: 14, marginTop: 4 }}>→ {t.desc}</div>
            </div>
          ))}
        </div>
      </FadeIn>
      <FadeIn delay={100}>
        <div
          style={{
            padding: "16px 24px",
            backgroundColor: C.card,
            border: `1px solid ${C.border}`,
            borderRadius: 8,
            fontFamily: "monospace",
            fontSize: 16,
            color: C.dim,
            textAlign: "center",
          }}
        >
          <div style={{ color: C.text, fontWeight: 600, marginBottom: 8 }}>Architecture</div>
          User Intent → MCP Server → Order Server → Solver Network
          <br />
          &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;↓
          <br />
          User receives tokens ← Oracle Verification ← Delivery
        </div>
      </FadeIn>
    </div>
  </AbsoluteFill>
);

const ClosingScene: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: C.bg, justifyContent: "center", alignItems: "center" }}>
    <FadeIn delay={5}>
      <div style={{ fontSize: 52, fontWeight: 800, color: C.blue, fontFamily: "monospace", textAlign: "center" }}>
        LI.FI Intents
      </div>
    </FadeIn>
    <FadeIn delay={25}>
      <div style={{ fontSize: 22, color: C.dim, fontFamily: "monospace", marginTop: 12, textAlign: "center" }}>
        Intent-Based Cross-Chain · MCP Protocol · AI Native
      </div>
    </FadeIn>
    <FadeIn delay={50}>
      <div style={{ fontSize: 18, color: C.text, fontFamily: "monospace", marginTop: 32, textAlign: "center" }}>
        Foundation of Open Intents Framework (OIF)
      </div>
      <div style={{ fontSize: 16, color: C.dim, fontFamily: "monospace", marginTop: 6, textAlign: "center" }}>
        by the Ethereum Foundation
      </div>
    </FadeIn>
    <FadeIn delay={80}>
      <div style={{ marginTop: 32, display: "flex", gap: 24, justifyContent: "center" }}>
        <div style={{ padding: "10px 20px", backgroundColor: C.card, border: `1px solid ${C.border}`, borderRadius: 8, fontFamily: "monospace", fontSize: 15, color: C.blue }}>
          docs.li.fi/lifi-intents
        </div>
        <div style={{ padding: "10px 20px", backgroundColor: C.card, border: `1px solid ${C.border}`, borderRadius: 8, fontFamily: "monospace", fontSize: 15, color: C.blue }}>
          intents-mcp.li.fi/mcp
        </div>
      </div>
    </FadeIn>
  </AbsoluteFill>
);

// ── Main composition ─────────────────────────────────────────────────

export const Demo: React.FC = () => {
  // Scene timings (frames at 30fps) — synced to narration audio
  // 01_intro:      0-150    (5.0s)
  // 02_question:  150-342   (6.4s)
  // 03_connect:   342-537   (6.5s)
  // 04_routes:    537-717   (6.0s)
  // 05_quote:     717-1023  (10.2s)
  // 06_explain:  1023-1473  (15.0s)
  // 07_mcp:      1473-1788  (10.5s)
  // 08_closing:  1788-2073  (9.5s)

  return (
    <AbsoluteFill style={{ backgroundColor: C.bg }}>
      {/* Audio tracks */}
      <Sequence from={0}>
        <Audio src={staticFile("audio/01_intro.mp3")} />
      </Sequence>
      <Sequence from={150}>
        <Audio src={staticFile("audio/02_question.mp3")} />
      </Sequence>
      <Sequence from={342}>
        <Audio src={staticFile("audio/03_connecting.mp3")} />
      </Sequence>
      <Sequence from={537}>
        <Audio src={staticFile("audio/04_routes.mp3")} />
      </Sequence>
      <Sequence from={717}>
        <Audio src={staticFile("audio/05_quote.mp3")} />
      </Sequence>
      <Sequence from={1023}>
        <Audio src={staticFile("audio/06_explain.mp3")} />
      </Sequence>
      <Sequence from={1473}>
        <Audio src={staticFile("audio/07_mcp.mp3")} />
      </Sequence>
      <Sequence from={1788}>
        <Audio src={staticFile("audio/08_closing.mp3")} />
      </Sequence>

      {/* Visual scenes */}
      <Sequence from={0} durationInFrames={150}>
        <IntroScene />
      </Sequence>
      <Sequence from={150} durationInFrames={192}>
        <QuestionScene />
      </Sequence>
      <Sequence from={342} durationInFrames={195}>
        <ConnectingScene />
      </Sequence>
      <Sequence from={537} durationInFrames={180}>
        <RoutesScene />
      </Sequence>
      <Sequence from={717} durationInFrames={306}>
        <QuoteScene />
      </Sequence>
      <Sequence from={1023} durationInFrames={450}>
        <ExplainScene />
      </Sequence>
      <Sequence from={1473} durationInFrames={315}>
        <McpScene />
      </Sequence>
      <Sequence from={1788} durationInFrames={312}>
        <ClosingScene />
      </Sequence>
    </AbsoluteFill>
  );
};
