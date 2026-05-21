import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  Sequence,
} from "remotion";

const COLORS = {
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

const Title: React.FC<{ text: string; sub?: string }> = ({ text, sub }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: "clamp" });
  const y = interpolate(frame, [0, 20], [30, 0], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: COLORS.bg,
        justifyContent: "center",
        alignItems: "center",
        opacity,
        transform: `translateY(${y}px)`,
      }}
    >
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 72, fontWeight: 800, color: COLORS.blue, fontFamily: "monospace" }}>
          {text}
        </div>
        {sub && (
          <div style={{ fontSize: 28, color: COLORS.dim, marginTop: 16, fontFamily: "monospace" }}>
            {sub}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};

const TerminalLine: React.FC<{
  text: string;
  color?: string;
  delay?: number;
  bold?: boolean;
}> = ({ text, color = COLORS.text, delay = 0, bold = false }) => {
  const frame = useCurrentFrame();
  const adjusted = frame - delay;
  if (adjusted < 0) return null;
  const opacity = interpolate(adjusted, [0, 10], [0, 1], { extrapolateRight: "clamp" });

  return (
    <div
      style={{
        fontFamily: "monospace",
        fontSize: 22,
        color,
        opacity,
        fontWeight: bold ? 700 : 400,
        lineHeight: 1.6,
        whiteSpace: "pre",
      }}
    >
      {text}
    </div>
  );
};

const Terminal: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div
      style={{
        backgroundColor: COLORS.card,
        border: `1px solid ${COLORS.border}`,
        borderRadius: 12,
        padding: 32,
        margin: "0 120px",
        minHeight: 500,
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
};

const StepCard: React.FC<{
  icon: string;
  title: string;
  desc: string;
  delay: number;
}> = ({ icon, title, desc, delay }) => {
  const frame = useCurrentFrame();
  const adjusted = frame - delay;
  if (adjusted < 0) return null;
  const opacity = interpolate(adjusted, [0, 15], [0, 1], { extrapolateRight: "clamp" });
  const x = interpolate(adjusted, [0, 15], [40, 0], { extrapolateRight: "clamp" });

  return (
    <div
      style={{
        opacity,
        transform: `translateX(${x}px)`,
        marginBottom: 24,
        display: "flex",
        gap: 16,
        alignItems: "flex-start",
      }}
    >
      <div style={{ fontSize: 36 }}>{icon}</div>
      <div>
        <div style={{ fontSize: 24, fontWeight: 700, color: COLORS.text, fontFamily: "monospace" }}>
          {title}
        </div>
        <div style={{ fontSize: 18, color: COLORS.dim, fontFamily: "monospace", marginTop: 4 }}>
          {desc}
        </div>
      </div>
    </div>
  );
};

export const Demo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Scene timings (in frames at 30fps)
  // 0-90: Title
  // 90-210: User question + agent response
  // 210-360: MCP tool calls
  // 360-540: Quote result
  // 540-720: Architecture explanation
  // 720-900: Closing

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg }}>
      {/* ── Title (0-3s) ─────────────────────────── */}
      <Sequence from={0} durationInFrames={90}>
        <Title text="LI.FI Intents × AI Agent" sub="MCP Protocol Cross-Chain Demo" />
      </Sequence>

      {/* ── User Question (3-7s) ─────────────────── */}
      <Sequence from={90} durationInFrames={120}>
        <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
          <Terminal>
            <TerminalLine text="$ hermes" color={COLORS.dim} delay={0} />
            <TerminalLine text="" delay={5} />
            <TerminalLine text="Builder:" color={COLORS.cyan} delay={10} bold />
            <TerminalLine
              text='I want to send 10 USDC from Base to Arbitrum.'
              delay={20}
            />
            <TerminalLine text="What's the best rate I can get?" delay={35} />
            <TerminalLine text="" delay={45} />
            <TerminalLine text="Hermes:" color={COLORS.purple} delay={50} bold />
            <TerminalLine text="Let me query the LI.FI Intents solver network." delay={60} />
          </Terminal>
        </AbsoluteFill>
      </Sequence>

      {/* ── MCP Tool Calls (7-12s) ───────────────── */}
      <Sequence from={210} durationInFrames={150}>
        <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
          <Terminal>
            <TerminalLine text="⚡ MCP → get-supported-routes" color={COLORS.yellow} delay={0} bold />
            <TerminalLine text="" delay={10} />
            <TerminalLine text="✓ 812+ active routes across 15+ chains" color={COLORS.green} delay={20} />
            <TerminalLine text="  Base, Arbitrum, Ethereum, Optimism..." color={COLORS.dim} delay={30} />
            <TerminalLine text="" delay={40} />
            <TerminalLine text="⚡ MCP → request-quote" color={COLORS.yellow} delay={50} bold />
            <TerminalLine text="  { fromChain: Base, toChain: Arbitrum," color={COLORS.dim} delay={65} />
            <TerminalLine text="    fromToken: USDC, amount: 10 }" color={COLORS.dim} delay={75} />
            <TerminalLine text="" delay={85} />
            <TerminalLine text="✓ Quote received from solver" color={COLORS.green} delay={95} bold />
            <TerminalLine text="  Input:  10 USDC" delay={105} />
            <TerminalLine text="  Output: 9.983725 USDC" color={COLORS.green} delay={115} />
            <TerminalLine text="  Fee:    ~0.016 USDC (0.16%)" color={COLORS.dim} delay={125} />
          </Terminal>
        </AbsoluteFill>
      </Sequence>

      {/* ── Architecture (12-20s) ────────────────── */}
      <Sequence from={540} durationInFrames={180}>
        <AbsoluteFill
          style={{ justifyContent: "center", alignItems: "center", padding: "0 120px" }}
        >
          <div style={{ width: "100%", maxWidth: 1200 }}>
            <div
              style={{
                fontSize: 40,
                fontWeight: 800,
                color: COLORS.blue,
                fontFamily: "monospace",
                marginBottom: 40,
                textAlign: "center",
              }}
            >
              How LI.FI Intents Works
            </div>

            <StepCard
              icon="1️⃣"
              title="Intent"
              desc='You say WHAT you want: "Send 10 USDC Base→Arbitrum"'
              delay={0}
            />
            <StepCard
              icon="2️⃣"
              title="Match"
              desc="Order server matches against solver standing quotes"
              delay={30}
            />
            <StepCard
              icon="3️⃣"
              title="Solve"
              desc="Best solver fills with their own capital — instant delivery"
              delay={60}
            />
            <StepCard
              icon="4️⃣"
              title="Settle"
              desc="On-chain verification. Solver reimbursed. You never wait."
              delay={90}
            />

            <div
              style={{
                marginTop: 40,
                padding: "16px 24px",
                backgroundColor: COLORS.card,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 8,
                fontFamily: "monospace",
                fontSize: 18,
                color: COLORS.dim,
                textAlign: "center",
                opacity: interpolate(
                  frame - 120,
                  [0, 15],
                  [0, 1],
                  { extrapolateRight: "clamp", extrapolateLeft: "clamp" }
                ),
              }}
            >
              User Intent → MCP Server → Order Server → Solver Network → Delivery
            </div>
          </div>
        </AbsoluteFill>
      </Sequence>

      {/* ── Closing (24-30s) ─────────────────────── */}
      <Sequence from={720} durationInFrames={180}>
        <AbsoluteFill
          style={{ justifyContent: "center", alignItems: "center", backgroundColor: COLORS.bg }}
        >
          <div style={{ textAlign: "center" }}>
            <div
              style={{
                fontSize: 56,
                fontWeight: 800,
                color: COLORS.blue,
                fontFamily: "monospace",
                opacity: interpolate(frame, [0, 20], [0, 1], { extrapolateRight: "clamp" }),
              }}
            >
              LI.FI Intents
            </div>
            <div
              style={{
                fontSize: 24,
                color: COLORS.dim,
                fontFamily: "monospace",
                marginTop: 16,
                opacity: interpolate(frame - 15, [0, 20], [0, 1], {
                  extrapolateRight: "clamp",
                  extrapolateLeft: "clamp",
                }),
              }}
            >
              Intent-Based Cross-Chain • MCP Protocol • AI Native
            </div>
            <div
              style={{
                fontSize: 20,
                color: COLORS.text,
                fontFamily: "monospace",
                marginTop: 40,
                opacity: interpolate(frame - 40, [0, 20], [0, 1], {
                  extrapolateRight: "clamp",
                  extrapolateLeft: "clamp",
                }),
              }}
            >
              Foundation of Open Intents Framework (OIF)
            </div>
            <div
              style={{
                fontSize: 18,
                color: COLORS.dim,
                fontFamily: "monospace",
                marginTop: 8,
                opacity: interpolate(frame - 50, [0, 20], [0, 1], {
                  extrapolateRight: "clamp",
                  extrapolateLeft: "clamp",
                }),
              }}
            >
              by the Ethereum Foundation
            </div>
            <div
              style={{
                marginTop: 40,
                display: "flex",
                gap: 32,
                justifyContent: "center",
                opacity: interpolate(frame - 70, [0, 20], [0, 1], {
                  extrapolateRight: "clamp",
                  extrapolateLeft: "clamp",
                }),
              }}
            >
              <div
                style={{
                  padding: "12px 24px",
                  backgroundColor: COLORS.card,
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: 8,
                  fontFamily: "monospace",
                  fontSize: 16,
                  color: COLORS.blue,
                }}
              >
                docs.li.fi/lifi-intents
              </div>
              <div
                style={{
                  padding: "12px 24px",
                  backgroundColor: COLORS.card,
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: 8,
                  fontFamily: "monospace",
                  fontSize: 16,
                  color: COLORS.blue,
                }}
              >
                intents-mcp.li.fi/mcp
              </div>
            </div>
          </div>
        </AbsoluteFill>
      </Sequence>
    </AbsoluteFill>
  );
};
