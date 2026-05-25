import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  Sequence,
  Audio,
  staticFile,
  Img,
} from "remotion";
import { AudioMix } from "./AudioMix";
import { Particles, GlowText } from "./components";

// ── Color Palette ──
const C = {
  bg: "#0d1117", card: "#161b22", border: "#30363d",
  text: "#e6edf3", dim: "#8b949e", blue: "#58a6ff",
  green: "#3fb950", yellow: "#d29922", red: "#f85149",
  purple: "#bc8cff", cyan: "#39d353", accent: "#4C64FF",
  white: "#ffffff",
};

// ═══════════════════════════════════════════════
// SHARED ANIMATION PRIMITIVES
// ═══════════════════════════════════════════════

/** Fade-in + slide-up with spring physics */
const SpringIn: React.FC<{
  children: React.ReactNode;
  delay?: number;
  direction?: "up" | "left" | "right" | "scale";
}> = ({ children, delay = 0, direction = "up" }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const df = Math.max(0, f - delay);
  const s = spring({ frame: df, fps, config: { damping: 14, stiffness: 120, mass: 0.8 } });
  const opacity = interpolate(s, [0, 1], [0, 1]);

  let transform = "";
  if (direction === "up") transform = `translateY(${interpolate(s, [0, 1], [40, 0])}px)`;
  if (direction === "left") transform = `translateX(${interpolate(s, [0, 1], [-60, 0])}px)`;
  if (direction === "right") transform = `translateX(${interpolate(s, [0, 1], [60, 0])}px)`;
  if (direction === "scale") {
    const sc = interpolate(s, [0, 1], [0.85, 1]);
    transform = `scale(${sc})`;
  }

  return <div style={{ opacity, transform }}>{children}</div>;
};

/** Fade in/out wrapper for entire scene */
const SceneTransition: React.FC<{
  children: React.ReactNode;
  fadeIn?: number;
  fadeOut?: number;
  totalFrames: number;
}> = ({ children, fadeIn = 20, fadeOut = 20, totalFrames }) => {
  const f = useCurrentFrame();
  const opacity = interpolate(
    f,
    [0, fadeIn, totalFrames - fadeOut, totalFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  return <div style={{ opacity }}>{children}</div>;
};

/** Glow line separator */
const GlowLine: React.FC<{ delay?: number; color?: string }> = ({ delay = 0, color = C.accent }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const df = Math.max(0, f - delay);
  const s = spring({ frame: df, fps, config: { damping: 20, stiffness: 100 } });
  const width = interpolate(s, [0, 1], [0, 100]);
  return (
    <div style={{
      width: `${width}%`, height: 2, margin: "16px auto",
      background: `linear-gradient(90deg, transparent, ${color}, transparent)`,
      borderRadius: 1,
    }} />
  );
};

/** Badge/Tag component */
const Badge: React.FC<{ text: string; color?: string; delay?: number }> = ({ text, color = C.blue, delay = 0 }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (f < delay) return null;
  const s = spring({ frame: f - delay, fps, config: { damping: 12 } });
  return (
    <div style={{
      opacity: s,
      transform: `scale(${interpolate(s, [0, 1], [0.7, 1])})`,
      padding: "6px 16px", borderRadius: 20,
      backgroundColor: `${color}18`, border: `1px solid ${color}40`,
      fontFamily: "'JetBrains Mono', monospace", fontSize: 13, color,
      fontWeight: 600, display: "inline-block",
    }}>
      {text}
    </div>
  );
};

// ═══════════════════════════════════════════════
// SCENE 1: CINEMATIC TITLE
// ═══════════════════════════════════════════════
const TitleScene: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Dramatic shield scale-in
  const shieldScale = spring({ frame: f, fps, config: { damping: 8, stiffness: 80 } });
  const shieldGlow = interpolate(f, [30, 80], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: C.bg, justifyContent: "center", alignItems: "center" }}>
      <Particles count={80} color={C.accent} speed={0.15} />

      {/* Radial glow background */}
      <div style={{
        position: "absolute", width: 600, height: 600, borderRadius: "50%",
        background: `radial-gradient(circle, ${C.accent}12 0%, transparent 70%)`,
        opacity: shieldGlow,
      }} />

      {/* Shield icon */}
      <div style={{
        fontSize: 72,
        transform: `scale(${shieldScale})`,
        marginBottom: 20,
      }}>🛡️</div>

      {/* Title */}
      <SpringIn delay={10} direction="up">
        <div style={{
          fontSize: 56, fontWeight: 900, fontFamily: "'JetBrains Mono', monospace",
          textAlign: "center", letterSpacing: -1,
        }}>
          <GlowText color={C.accent}>LI.FI Intents</GlowText>
        </div>
      </SpringIn>

      {/* Subtitle */}
      <SpringIn delay={25} direction="up">
        <div style={{
          fontSize: 28, fontWeight: 600, color: C.text,
          fontFamily: "'JetBrains Mono', monospace", marginTop: 8, textAlign: "center",
        }}>
          Developer Playground
        </div>
      </SpringIn>

      {/* Divider */}
      <GlowLine delay={40} />

      {/* Feature badges */}
      <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
        <Badge text="Safe Verdict" color={C.green} delay={50} />
        <Badge text="MCP Protocol" color={C.blue} delay={60} />
        <Badge text="Cross-Chain" color={C.purple} delay={70} />
        <Badge text="Solver-Aware" color={C.cyan} delay={80} />
      </div>

      {/* Footer link */}
      <SpringIn delay={100}>
        <div style={{
          fontSize: 14, color: C.dim, fontFamily: "'JetBrains Mono', monospace",
          marginTop: 40, textAlign: "center", opacity: 0.6,
        }}>
          lifi.degure.me · docs.li.fi/lifi-intents
        </div>
      </SpringIn>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════
// SCENE 2: WEB UI — HOMEPAGE SHOWCASE
// ═══════════════════════════════════════════════
const WebUIHomeScene: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Screenshot zoom-in from center
  const imgScale = spring({ frame: f, fps, config: { damping: 15, stiffness: 80 } });
  const imgOp = interpolate(f, [0, 20], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: C.bg, justifyContent: "center", alignItems: "center" }}>
      {/* Label */}
      <SpringIn delay={0}>
        <div style={{
          fontSize: 18, color: C.dim, fontFamily: "'JetBrains Mono', monospace",
          marginBottom: 20, textAlign: "center",
        }}>
          🌐 Web Interface — lifi.degure.me
        </div>
      </SpringIn>

      {/* Screenshot with glow border */}
      <div style={{
        opacity: imgOp,
        transform: `scale(${interpolate(imgScale, [0, 1], [0.9, 1])})`,
        borderRadius: 16, overflow: "hidden",
        border: `1px solid ${C.border}`,
        boxShadow: `0 0 60px ${C.accent}15, 0 20px 60px rgba(0,0,0,0.5)`,
      }}>
        <Img src={staticFile("recordings/ui-homepage.png")} style={{ width: 1600, height: 900, objectFit: "cover" }} />
      </div>

      {/* Feature callouts */}
      <div style={{ display: "flex", gap: 24, marginTop: 20 }}>
        <SpringIn delay={30}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 20 }}>📝</div>
            <div style={{ fontSize: 12, color: C.dim, fontFamily: "'JetBrains Mono', monospace" }}>Natural Language Input</div>
          </div>
        </SpringIn>
        <SpringIn delay={40}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 20 }}>🎯</div>
            <div style={{ fontSize: 12, color: C.dim, fontFamily: "'JetBrains Mono', monospace" }}>10 Policy Presets</div>
          </div>
        </SpringIn>
        <SpringIn delay={50}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 20 }}>🔌</div>
            <div style={{ fontSize: 12, color: C.dim, fontFamily: "'JetBrains Mono', monospace" }}>Live MCP Connection</div>
          </div>
        </SpringIn>
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════
// SCENE 3: WEB UI — PRESET CARDS SHOWCASE
// ═══════════════════════════════════════════════
const WebUIPresetsScene: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();

  const presets = [
    { name: "safe-transfer", status: "EXECUTABLE", emoji: "🟢" },
    { name: "fee-check", status: "EXECUTABLE", emoji: "🟢" },
    { name: "cheapest-route", status: "EXECUTABLE", emoji: "🟢" },
    { name: "health-check", status: "REFUSED", emoji: "🔴" },
    { name: "avoid-chain", status: "REFUSED", emoji: "🔴" },
    { name: "no-quote", status: "REFUSED", emoji: "🔴" },
    { name: "strict-fee-check", status: "REFUSED", emoji: "🔴" },
    { name: "fee-too-high", status: "REFUSED", emoji: "🔴" },
    { name: "min-output", status: "REFUSED", emoji: "🔴" },
    { name: "multi-constraint", status: "REFUSED", emoji: "🔴" },
  ];

  return (
    <AbsoluteFill style={{ backgroundColor: C.bg, justifyContent: "center", alignItems: "center" }}>
      <Particles count={40} color={C.accent} speed={0.1} />

      <SpringIn delay={0}>
        <div style={{
          fontSize: 24, fontWeight: 700, color: C.text,
          fontFamily: "'JetBrains Mono', monospace", marginBottom: 24, textAlign: "center",
        }}>
          🎯 10 Policy Presets — One Click Testing
        </div>
      </SpringIn>

      {/* Staggered preset cards — 2 rows */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10, width: 1000 }}>
        {[0, 1].map(row => (
          <div key={row} style={{ display: "flex", gap: 10, justifyContent: "center" }}>
            {presets.slice(row * 5, row * 5 + 5).map((p, i) => {
              const idx = row * 5 + i;
              const delay = 15 + idx * 8;
              const { fps } = useVideoConfig();
              const s = spring({ frame: Math.max(0, f - delay), fps, config: { damping: 12, stiffness: 150 } });
              const isExec = p.status === "EXECUTABLE";

              return (
                <div key={idx} style={{
                  opacity: s,
                  transform: `translateY(${interpolate(s, [0, 1], [30, 0])}px) scale(${interpolate(s, [0, 1], [0.9, 1])})`,
                  padding: "14px 18px",
                  backgroundColor: C.card,
                  border: `1px solid ${isExec ? C.green + "40" : C.red + "40"}`,
                  borderRadius: 10,
                  fontFamily: "'JetBrains Mono', monospace",
                  minWidth: 160, textAlign: "center",
                  boxShadow: isExec ? `0 0 20px ${C.green}10` : `0 0 20px ${C.red}10`,
                }}>
                  <div style={{ fontSize: 14, color: C.text, fontWeight: 600 }}>
                    {p.emoji} {p.name}
                  </div>
                  <div style={{
                    fontSize: 11, fontWeight: 700, marginTop: 4,
                    color: isExec ? C.green : C.red,
                  }}>
                    {p.status}
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* Summary badge */}
      <SpringIn delay={110}>
        <div style={{
          marginTop: 24, display: "flex", gap: 20, justifyContent: "center",
          fontFamily: "'JetBrains Mono', monospace", fontSize: 14,
        }}>
          <span style={{ color: C.green }}>✅ 3 EXECUTABLE</span>
          <span style={{ color: C.dim }}>·</span>
          <span style={{ color: C.red }}>🚫 7 REFUSED</span>
        </div>
      </SpringIn>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════
// SCENE 4: WEB UI — DECISION TRACE (ANALYZE)
// ═══════════════════════════════════════════════
const WebUITraceScene: React.FC = () => {
  const f = useCurrentFrame();

  return (
    <AbsoluteFill style={{ backgroundColor: C.bg, justifyContent: "center", alignItems: "center" }}>
      <SpringIn delay={0}>
        <div style={{
          fontSize: 20, color: C.dim, fontFamily: "'JetBrains Mono', monospace",
          marginBottom: 16, textAlign: "center",
        }}>
          🔍 Decision Trace — Real Analysis
        </div>
      </SpringIn>

      <SpringIn delay={15} direction="scale">
        <div style={{
          borderRadius: 16, overflow: "hidden",
          border: `1px solid ${C.green}40`,
          boxShadow: `0 0 80px ${C.green}12, 0 20px 60px rgba(0,0,0,0.5)`,
        }}>
          <Img src={staticFile("recordings/ui-result-executable.png")} style={{ width: 1600, height: 900, objectFit: "cover" }} />
        </div>
      </SpringIn>

      {/* Verdict badge */}
      <SpringIn delay={40}>
        <Badge text="✅ EXECUTABLE — Fee 0.20% within limits" color={C.green} />
      </SpringIn>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════
// SCENE 5: CLI TERMINAL — REAL DATA
// ═══════════════════════════════════════════════
const CLIScene: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Typewriter effect
  const lines = [
    { text: "$ python3 -m lifi_agent", color: C.dim, delay: 0, bold: false },
    { text: "", color: C.text, delay: 8, bold: false },
    { text: "❯ send 0.001 WETH from Base to Arbitrum", color: C.cyan, delay: 15, bold: true },
    { text: "", color: C.text, delay: 25, bold: false },
    { text: "  Intent: 0.001 ETH base → arbitrum", color: C.dim, delay: 30, bold: false },
    { text: "", color: C.text, delay: 38, bold: false },
    { text: "  ⚡ check-route-health", color: C.yellow, delay: 45, bold: true },
    { text: "    ✓ Route Supported", color: C.green, delay: 60, bold: false },
    { text: "    Matching Routes: 5", color: C.text, delay: 70, bold: false },
    { text: "    Recent Orders: 10 (9 settled)", color: C.text, delay: 80, bold: false },
    { text: "    Latest: Settled @ 2026-05-25T13:20", color: C.green, delay: 90, bold: false },
    { text: "", color: C.text, delay: 100, bold: false },
    { text: "  ⚡ request-quote", color: C.yellow, delay: 110, bold: true },
    { text: "    Quote: 0.988747 USDC (fee 1.13%)", color: C.text, delay: 125, bold: false },
    { text: "    Verdict: EXECUTABLE ✅", color: C.green, delay: 140, bold: true },
  ];

  return (
    <AbsoluteFill style={{ backgroundColor: C.bg, justifyContent: "center", alignItems: "center" }}>
      {/* Terminal window */}
      <SpringIn delay={0} direction="scale">
        <div style={{
          width: 1500, backgroundColor: C.card,
          border: `1px solid ${C.border}`, borderRadius: 16,
          padding: 28, boxShadow: `0 0 60px rgba(0,0,0,0.4), 0 0 30px ${C.accent}08`,
        }}>
          {/* Window dots */}
          <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
            <div style={{ width: 14, height: 14, borderRadius: 7, backgroundColor: "#ff5f56" }} />
            <div style={{ width: 14, height: 14, borderRadius: 7, backgroundColor: "#ffbd2e" }} />
            <div style={{ width: 14, height: 14, borderRadius: 7, backgroundColor: "#27c93f" }} />
            <div style={{ marginLeft: 16, fontSize: 12, color: C.dim, fontFamily: "'JetBrains Mono', monospace", lineHeight: "14px" }}>
              lifi-agent — MCP CLI
            </div>
          </div>

          {/* Terminal lines with staggered reveal */}
          {lines.map((line, i) => {
            if (f < line.delay) return null;
            const lineOp = interpolate(f - line.delay, [0, 8], [0, 1], { extrapolateRight: "clamp" });
            const lineX = interpolate(f - line.delay, [0, 8], [10, 0], { extrapolateRight: "clamp" });

            return (
              <div key={i} style={{
                opacity: lineOp,
                transform: `translateX(${lineX}px)`,
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 18, color: line.color,
                fontWeight: line.bold ? 700 : 400,
                lineHeight: 1.8, whiteSpace: "pre",
              }}>
                {line.text}
              </div>
            );
          })}

          {/* Blinking cursor */}
          {f > 0 && (
            <span style={{
              opacity: Math.floor(f / 15) % 2 === 0 ? 1 : 0,
              color: C.cyan, fontFamily: "'JetBrains Mono', monospace", fontSize: 18,
            }}>▌</span>
          )}
        </div>
      </SpringIn>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════
// SCENE 6: DECISION TRACE — EXECUTABLE
// ═══════════════════════════════════════════════
const VerdictPassScene: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();

  const steps = [
    { icon: "✅", name: "Parse Intent", detail: "Valid cross-chain request" },
    { icon: "✅", name: "Parse Policy", detail: "Policy(fee<0.5%, healthy route)" },
    { icon: "✅", name: "Route Health", detail: "Status: HEALTHY" },
    { icon: "✅", name: "Fee Policy", detail: "0.20% < 0.5% max" },
    { icon: "✅", name: "Quote Available", detail: "Solver quote available" },
    { icon: "✅", name: "Final Verdict", detail: "All checks passed ✓" },
  ];

  // Animated progress bar
  const progress = interpolate(f, [0, 120], [0, 1], { extrapolateRight: "clamp" });
  // Animated fee counter
  const feeValue = interpolate(f, [130, 160], [0, 0.2], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: C.bg, justifyContent: "center", alignItems: "center" }}>
      <div style={{ width: 1400, padding: "0 80px" }}>
        <SpringIn delay={0}>
          <div style={{
            fontSize: 22, fontWeight: 700, color: C.text,
            fontFamily: "'JetBrains Mono', monospace", marginBottom: 20, textAlign: "center",
          }}>
            🛡️ Safe Verdict — Decision Trace
          </div>
        </SpringIn>

        {/* Animated progress bar */}
        <SpringIn delay={5}>
          <div style={{ marginBottom: 20 }}>
            <div style={{
              display: "flex", justifyContent: "space-between", marginBottom: 6,
              fontFamily: "'JetBrains Mono', monospace", fontSize: 13, color: C.dim,
            }}>
              <span>Analysis Progress</span>
              <span>{Math.round(progress * 100)}%</span>
            </div>
            <div style={{
              width: "100%", height: 6, borderRadius: 3,
              backgroundColor: "rgba(255,255,255,0.06)", overflow: "hidden",
            }}>
              <div style={{
                width: `${progress * 100}%`, height: "100%", borderRadius: 3,
                backgroundColor: C.green, boxShadow: `0 0 10px ${C.green}40`,
              }} />
            </div>
          </div>
        </SpringIn>

        <div style={{
          backgroundColor: C.card, border: `1px solid ${C.border}`,
          borderRadius: 12, padding: 28,
        }}>
          {steps.map((step, i) => {
            const delay = 15 + i * 18;
            const s = spring({ frame: Math.max(0, f - delay), fps, config: { damping: 14, stiffness: 130 } });
            if (f < delay) return null;

            return (
              <div key={i} style={{
                opacity: s,
                transform: `translateX(${interpolate(s, [0, 1], [30, 0])}px)`,
                display: "flex", gap: 12, marginBottom: 10,
                fontFamily: "'JetBrains Mono', monospace", fontSize: 17,
                padding: "10px 16px", borderRadius: 8,
                backgroundColor: f > delay + 10 ? `${C.green}08` : "transparent",
              }}>
                <span>{step.icon}</span>
                <span style={{ color: C.text, width: 180, fontWeight: 600 }}>{step.name}</span>
                <span style={{ color: C.green, fontWeight: 700, width: 130 }}>EXECUTABLE</span>
                <span style={{ color: C.dim }}>{step.detail}</span>
              </div>
            );
          })}
        </div>

        {/* Final verdict with animated fee counter */}
        <SpringIn delay={130} direction="scale">
          <div style={{
            marginTop: 16, padding: "16px 32px",
            backgroundColor: `${C.green}10`, border: `2px solid ${C.green}`,
            borderRadius: 12, textAlign: "center",
            boxShadow: `0 0 40px ${C.green}15`,
          }}>
            <div style={{
              fontSize: 30, fontWeight: 900, color: C.green,
              fontFamily: "'JetBrains Mono', monospace",
            }}>✅ EXECUTABLE</div>
            <div style={{
              fontSize: 16, color: C.text,
              fontFamily: "'JetBrains Mono', monospace", marginTop: 6,
              fontVariantNumeric: "tabular-nums",
            }}>
              Fee: <span style={{ color: C.green, fontWeight: 700 }}>{feeValue.toFixed(2)}%</span>
              {" "}≤ 0.5% limit
            </div>
            <div style={{
              fontSize: 13, color: C.dim,
              fontFamily: "'JetBrains Mono', monospace", marginTop: 4,
            }}>Safe to proceed — all policy checks passed</div>
          </div>
        </SpringIn>
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════
// SCENE 7: DECISION TRACE — REFUSED
// ═══════════════════════════════════════════════
const VerdictFailScene: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();

  const steps = [
    { icon: "✅", name: "Parse Intent", verdict: "PASS", detail: "Valid request", color: C.green },
    { icon: "✅", name: "Parse Policy", verdict: "PASS", detail: "Policy(max_fee=0.5%)", color: C.green },
    { icon: "🚫", name: "Route Health", verdict: "REFUSED", detail: "No active solvers for Base→Tron", color: C.red },
    { icon: "🚫", name: "Fee Policy", verdict: "REFUSED", detail: "8.5% > 0.5% max fee", color: C.red },
    { icon: "🚫", name: "Quote Available", verdict: "REFUSED", detail: "No solver coverage", color: C.red },
    { icon: "🚫", name: "Final Verdict", verdict: "REFUSED", detail: "Policy violations detected ✗", color: C.red },
  ];

  return (
    <AbsoluteFill style={{ backgroundColor: C.bg, justifyContent: "center", alignItems: "center" }}>
      <div style={{ width: 1400, padding: "0 80px" }}>
        {/* Input echo */}
        <SpringIn delay={0}>
          <div style={{
            fontSize: 15, color: C.dim, fontFamily: "'JetBrains Mono', monospace",
            marginBottom: 16, textAlign: "center", opacity: 0.7,
          }}>
            ❯ safe send 100 USDC from Base to Tron if fee &lt; 0.5%
          </div>
        </SpringIn>

        <div style={{
          backgroundColor: C.card, border: `1px solid ${C.border}`,
          borderRadius: 12, padding: 28,
        }}>
          {steps.map((step, i) => {
            const delay = 15 + i * 18;
            const s = spring({ frame: Math.max(0, f - delay), fps, config: { damping: 14, stiffness: 130 } });
            if (f < delay) return null;

            return (
              <div key={i} style={{
                opacity: s,
                transform: `translateX(${interpolate(s, [0, 1], [30, 0])}px)`,
                display: "flex", gap: 12, marginBottom: 10,
                fontFamily: "'JetBrains Mono', monospace", fontSize: 17,
                padding: "10px 16px", borderRadius: 8,
                backgroundColor: step.color === C.red ? `${C.red}08` : `${C.green}08`,
              }}>
                <span>{step.icon}</span>
                <span style={{ color: C.text, width: 180, fontWeight: 600 }}>{step.name}</span>
                <span style={{ color: step.color, fontWeight: 700, width: 130 }}>{step.verdict}</span>
                <span style={{ color: C.dim }}>{step.detail}</span>
              </div>
            );
          })}
        </div>

        {/* Final verdict banner */}
        <SpringIn delay={130} direction="scale">
          <div style={{
            marginTop: 16, padding: "16px 32px",
            backgroundColor: `${C.red}10`, border: `2px solid ${C.red}`,
            borderRadius: 12, textAlign: "center",
            boxShadow: `0 0 40px ${C.red}15`,
          }}>
            <div style={{
              fontSize: 30, fontWeight: 900, color: C.red,
              fontFamily: "'JetBrains Mono', monospace",
            }}>🚫 REFUSED</div>
            <div style={{
              fontSize: 14, color: C.dim,
              fontFamily: "'JetBrains Mono', monospace", marginTop: 6,
            }}>Policy violation: no solver coverage + fee too high</div>
          </div>
        </SpringIn>
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════
// SCENE 8: MCP PROOF
// ═══════════════════════════════════════════════
const MCPProofScene: React.FC = () => {
  const f = useCurrentFrame();

  return (
    <AbsoluteFill style={{ backgroundColor: C.bg, justifyContent: "center", alignItems: "center" }}>
      <SpringIn delay={0}>
        <div style={{
          fontSize: 22, fontWeight: 700, color: C.text,
          fontFamily: "'JetBrains Mono', monospace", marginBottom: 20, textAlign: "center",
        }}>
          🔗 MCP Proof — Real Server Connection
        </div>
      </SpringIn>

      <SpringIn delay={15} direction="scale">
        <div style={{
          borderRadius: 16, overflow: "hidden",
          border: `1px solid ${C.accent}40`,
          boxShadow: `0 0 80px ${C.accent}15, 0 20px 60px rgba(0,0,0,0.5)`,
        }}>
          <Img src={staticFile("recordings/ui-mcp-proof.png")} style={{ width: 1600, height: 900, objectFit: "cover" }} />
        </div>
      </SpringIn>

      {/* Proof details */}
      <div style={{ display: "flex", gap: 20, marginTop: 20 }}>
        <SpringIn delay={40}>
          <Badge text="Connected to Real MCP" color={C.green} />
        </SpringIn>
        <SpringIn delay={50}>
          <Badge text="75 Routes Available" color={C.blue} />
        </SpringIn>
        <SpringIn delay={60}>
          <Badge text="Live Quote: 0.988 USDC" color={C.cyan} />
        </SpringIn>
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════
// SCENE 9: ARCHITECTURE
// ═══════════════════════════════════════════════
const ArchScene: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();

  const flowSteps = [
    { emoji: "🎯", label: "User Goal", sub: "natural language", color: C.text },
    { emoji: "🧠", label: "AI Agent", sub: "parse → policy", color: C.purple },
    { emoji: "🔌", label: "MCP Server", sub: "LI.FI Intents API", color: C.yellow },
    { emoji: "💱", label: "Solver Network", sub: "compete on price", color: C.green },
    { emoji: "🛡️", label: "Safe Verdict", sub: "EXECUTABLE or REFUSED", color: C.accent },
  ];

  const mcpTools = [
    { name: "get-supported-routes", desc: "Discover" },
    { name: "request-quote", desc: "Price" },
    { name: "check-route-health", desc: "Health" },
    { name: "prepare-order", desc: "Build" },
    { name: "track-order", desc: "Monitor" },
  ];

  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", padding: "0 100px" }}>
      <Particles count={30} color={C.accent} speed={0.1} />

      <SpringIn delay={0}>
        <div style={{
          fontSize: 24, fontWeight: 700, color: C.text,
          fontFamily: "'JetBrains Mono', monospace", marginBottom: 28, textAlign: "center",
        }}>
          Architecture: AI Agent × Cross-Chain
        </div>
      </SpringIn>

      {/* Flow diagram — horizontal */}
      <div style={{ display: "flex", alignItems: "center", gap: 0 }}>
        {flowSteps.map((step, i) => {
          const delay = 20 + i * 20;
          const s = spring({ frame: Math.max(0, f - delay), fps, config: { damping: 12, stiffness: 120 } });
          if (f < delay) return null;

          return (
            <React.Fragment key={i}>
              <div style={{
                opacity: s,
                transform: `scale(${interpolate(s, [0, 1], [0.8, 1])})`,
                padding: "20px 28px", backgroundColor: C.card,
                border: `1px solid ${step.color}30`, borderRadius: 12,
                textAlign: "center", minWidth: 160,
                boxShadow: `0 0 20px ${step.color}10`,
              }}>
                <div style={{ fontSize: 28, marginBottom: 6 }}>{step.emoji}</div>
                <div style={{
                  fontSize: 15, fontWeight: 700, color: step.color,
                  fontFamily: "'JetBrains Mono', monospace",
                }}>{step.label}</div>
                <div style={{
                  fontSize: 11, color: C.dim,
                  fontFamily: "'JetBrains Mono', monospace", marginTop: 4,
                }}>{step.sub}</div>
              </div>
              {i < flowSteps.length - 1 && (
                <SpringIn delay={delay + 10}>
                  <div style={{
                    fontSize: 24, color: C.dim, margin: "0 8px",
                    fontFamily: "'JetBrains Mono', monospace",
                  }}>→</div>
                </SpringIn>
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* MCP Tools row */}
      <SpringIn delay={130}>
        <div style={{
          display: "flex", gap: 12, marginTop: 32, justifyContent: "center", flexWrap: "wrap",
        }}>
          {mcpTools.map((t, i) => (
            <div key={i} style={{
              padding: "10px 18px", backgroundColor: C.card,
              border: `1px solid ${C.border}`, borderRadius: 8,
              fontFamily: "'JetBrains Mono', monospace", textAlign: "center",
            }}>
              <div style={{ color: C.cyan, fontSize: 13, fontWeight: 600 }}>{t.name}</div>
              <div style={{ color: C.dim, fontSize: 11, marginTop: 2 }}>→ {t.desc}</div>
            </div>
          ))}
        </div>
      </SpringIn>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════
// SCENE 10: CLOSING
// ═══════════════════════════════════════════════
const CloseScene: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();

  const pulseScale = 1 + Math.sin(f * 0.05) * 0.02;

  return (
    <AbsoluteFill style={{ backgroundColor: C.bg, justifyContent: "center", alignItems: "center" }}>
      <Particles count={80} color={C.accent} speed={0.2} />

      {/* Radial glow */}
      <div style={{
        position: "absolute", width: 500, height: 500, borderRadius: "50%",
        background: `radial-gradient(circle, ${C.accent}15 0%, transparent 70%)`,
      }} />

      <SpringIn delay={5} direction="scale">
        <div style={{
          fontSize: 52, fontWeight: 900, fontFamily: "'JetBrains Mono', monospace",
          textAlign: "center", transform: `scale(${pulseScale})`,
        }}>
          <GlowText color={C.accent}>🛡️ LI.FI Intents</GlowText>
        </div>
      </SpringIn>

      <SpringIn delay={20}>
        <div style={{
          fontSize: 22, color: C.text, fontFamily: "'JetBrains Mono', monospace",
          marginTop: 12, textAlign: "center", fontWeight: 600,
        }}>
          Developer Playground
        </div>
      </SpringIn>

      <GlowLine delay={35} />

      <SpringIn delay={50}>
        <div style={{
          fontSize: 16, color: C.dim, fontFamily: "'JetBrains Mono', monospace",
          textAlign: "center",
        }}>
          Policy-driven cross-chain decisions for AI Agents
        </div>
      </SpringIn>

      <div style={{ display: "flex", gap: 16, marginTop: 28 }}>
        <SpringIn delay={70}>
          <div style={{
            padding: "10px 24px", backgroundColor: C.card,
            border: `1px solid ${C.border}`, borderRadius: 10,
            fontFamily: "'JetBrains Mono', monospace", fontSize: 14, color: C.blue,
          }}>docs.li.fi/lifi-intents</div>
        </SpringIn>
        <SpringIn delay={80}>
          <div style={{
            padding: "10px 24px", backgroundColor: C.card,
            border: `1px solid ${C.border}`, borderRadius: 10,
            fontFamily: "'JetBrains Mono', monospace", fontSize: 14, color: C.blue,
          }}>lifi.degure.me</div>
        </SpringIn>
        <SpringIn delay={90}>
          <div style={{
            padding: "10px 24px", backgroundColor: C.card,
            border: `1px solid ${C.border}`, borderRadius: 10,
            fontFamily: "'JetBrains Mono', monospace", fontSize: 14, color: C.blue,
          }}>github.com/tiyadegure</div>
        </SpringIn>
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════
// MAIN COMPOSITION
// ═══════════════════════════════════════════════
export const Demo: React.FC = () => {
  // Scene timing — natural MiMo TTS (Dean, speed=1.2)
  // Scene durations in frames (30fps):
  const scenes = [
    { start: 0,    dur: 342,  Component: TitleScene },
    { start: 342,  dur: 328,  Component: WebUIHomeScene },
    { start: 670,  dur: 303,  Component: WebUIPresetsScene },
    { start: 973,  dur: 200,  Component: WebUITraceScene },
    { start: 1173, dur: 310,  Component: CLIScene },
    { start: 1483, dur: 524,  Component: VerdictPassScene },
    { start: 2007, dur: 582,  Component: VerdictFailScene },
    { start: 2589, dur: 300,  Component: MCPProofScene },
    { start: 2889, dur: 400,  Component: ArchScene },
    { start: 3289, dur: 452,  Component: CloseScene },
  ];

  const totalFrames = scenes[scenes.length - 1].start + scenes[scenes.length - 1].dur;

  return (
    <AbsoluteFill style={{ backgroundColor: C.bg }}>
      <AudioMix />

      {/* Narration audio — MiMo TTS (Dean, speed=1.2)
          Each audio starts at its scene's exact start frame.
          Audio trimmed to fit scene duration — NO overlap. */}
      <Sequence from={0}><Audio src={staticFile("audio/01_intro.mp3")} /></Sequence>          {/* TitleScene 0-342 (11.4s) */}
      <Sequence from={342}><Audio src={staticFile("audio/02_webui.mp3")} /></Sequence>        {/* WebUIHome 342-670 (10.9s) */}
      <Sequence from={670}><Audio src={staticFile("audio/03_preset.mp3")} /></Sequence>       {/* WebUIPresets 670-973 (10.1s) */}
      {/* WebUITraceScene 973-1173: visual-only, no narration */}
      <Sequence from={1173}><Audio src={staticFile("audio/04_cli_trimmed.mp3")} /></Sequence>   {/* CLIScene 1173-1483 (10s trimmed) */}
      <Sequence from={1483}><Audio src={staticFile("audio/05_verdict_ok.mp3")} /></Sequence>  {/* VerdictPass 1483-2007 (12.7s) */}
      <Sequence from={2007}><Audio src={staticFile("audio/06_verdict_no.mp3")} /></Sequence>  {/* VerdictFail 2007-2589 (19.4s) */}
      <Sequence from={2589}><Audio src={staticFile("audio/07_mcp_proof.mp3")} /></Sequence>   {/* MCPProof 2589-2889 (9.5s trimmed) */}
      <Sequence from={2889}><Audio src={staticFile("audio/08_arch_trimmed.mp3")} /></Sequence> {/* ArchScene 2889-3289 (13s trimmed) */}
      <Sequence from={3289}><Audio src={staticFile("audio/09_closing.mp3")} /></Sequence>     {/* CloseScene 3289-3741 (15.1s) */}

      {/* Scenes with fade transitions */}
      {scenes.map((scene, i) => (
        <Sequence key={i} from={scene.start} durationInFrames={scene.dur}>
          <SceneTransition totalFrames={scene.dur} fadeIn={15} fadeOut={15}>
            <scene.Component />
          </SceneTransition>
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
