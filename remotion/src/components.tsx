import React, { useMemo } from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from "remotion";

/**
 * Particles — Floating background particles for tech/sci-fi feel.
 * Uses deterministic seed positions to avoid re-computation per frame.
 */
export const Particles: React.FC<{
  count?: number;
  color?: string;
  speed?: number;
  size?: [number, number];
}> = ({ count = 40, color = "#4C64FF", speed = 0.3, size = [2, 5] }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const particles = useMemo(() => {
    return Array.from({ length: count }, (_, i) => ({
      x: (i * 137.508) % width,
      y: (i * 271.317) % height,
      size: size[0] + (i % (size[1] - size[0] + 1)),
      speed: 0.2 + (i % 10) * 0.08,
      phase: (i * 0.7) % (Math.PI * 2),
    }));
  }, [count, width, height, size]);

  return (
    <AbsoluteFill style={{ overflow: "hidden", pointerEvents: "none" }}>
      {particles.map((p, i) => {
        const y = (p.y + frame * p.speed * speed) % (height + 20) - 10;
        const x = p.x + Math.sin(frame * 0.015 + p.phase) * 25;
        const opacity = 0.08 + Math.sin(frame * 0.02 + p.phase) * 0.05;

        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: x,
              top: y,
              width: p.size,
              height: p.size,
              borderRadius: "50%",
              backgroundColor: color,
              opacity,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

/**
 * TypewriterText — Character-by-character text reveal with cursor.
 */
export const TypewriterText: React.FC<{
  text: string;
  charsPerSecond?: number;
  cursor?: boolean;
  style?: React.CSSProperties;
}> = ({ text, charsPerSecond = 30, cursor = true, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const charsPerFrame = charsPerSecond / fps;
  const visibleChars = Math.floor(frame * charsPerFrame);
  const visibleText = text.slice(0, Math.min(visibleChars, text.length));
  const isTyping = visibleChars < text.length;

  const cursorOpacity = isTyping
    ? 1
    : Math.floor(frame / (fps * 0.5)) % 2 === 0
      ? 1
      : 0;

  return (
    <span
      style={{
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        ...style,
      }}
    >
      {visibleText}
      {cursor && (
        <span style={{ opacity: cursorOpacity, color: style?.color || "#58a6ff" }}>
          ▌
        </span>
      )}
    </span>
  );
};

/**
 * AnimatedProgress — Progress bar with percentage label.
 */
export const AnimatedProgress: React.FC<{
  from: number;
  to: number;
  durationFrames: number;
  label?: string;
  color?: string;
  height?: number;
  delay?: number;
}> = ({
  from,
  to,
  durationFrames,
  label = "Progress",
  color = "#4C64FF",
  height = 6,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  const adjusted = Math.max(0, frame - delay);
  const progress = interpolate(adjusted, [0, durationFrames], [from, to], {
    extrapolateRight: "clamp",
  });

  return (
    <div style={{ width: "100%", opacity: adjusted > 0 ? 1 : 0 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: 6,
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 14,
          color: "#8b949e",
        }}
      >
        <span>{label}</span>
        <span>{Math.round(progress * 100)}%</span>
      </div>
      <div
        style={{
          width: "100%",
          height,
          borderRadius: height / 2,
          backgroundColor: "rgba(255,255,255,0.06)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${progress * 100}%`,
            height: "100%",
            borderRadius: height / 2,
            backgroundColor: color,
          }}
        />
      </div>
    </div>
  );
};

/**
 * StaggeredList — List items that spring in one by one.
 */
export const StaggeredList: React.FC<{
  items: { text: string; color?: string }[];
  staggerFrames?: number;
  baseDelay?: number;
  fontSize?: number;
}> = ({ items, staggerFrames = 8, baseDelay = 0, fontSize = 18 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {items.map((item, i) => {
        const delay = baseDelay + i * staggerFrames;
        const t = Math.max(0, frame - delay);
        // Simple spring approximation
        const raw = interpolate(t, [0, 12], [0, 1], { extrapolateRight: "clamp" });
        const overshoot = Math.sin(t * 0.3) * Math.max(0, 1 - t / 20) * 0.1;
        const s = raw + overshoot;
        const opacity = interpolate(s, [0, 1], [0, 1], { extrapolateRight: "clamp" });
        const x = interpolate(s, [0, 1], [40, 0], { extrapolateRight: "clamp" });

        return (
          <div
            key={i}
            style={{
              opacity,
              transform: `translateX(${x}px)`,
              fontSize,
              color: item.color || "#c9d1d9",
              fontFamily: "'JetBrains Mono', monospace",
              lineHeight: 1.5,
            }}
          >
            {item.text}
          </div>
        );
      })}
    </div>
  );
};

/**
 * AnimatedCounter — Number that counts up over time.
 */
export const AnimatedCounter: React.FC<{
  from: number;
  to: number;
  durationFrames: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  delay?: number;
  style?: React.CSSProperties;
}> = ({
  from,
  to,
  durationFrames,
  prefix = "",
  suffix = "",
  decimals = 0,
  delay = 0,
  style,
}) => {
  const frame = useCurrentFrame();
  const adjusted = Math.max(0, frame - delay);
  const value = interpolate(adjusted, [0, durationFrames], [from, to], {
    extrapolateRight: "clamp",
  });

  return (
    <span
      style={{
        fontVariantNumeric: "tabular-nums",
        fontFamily: "'JetBrains Mono', monospace",
        ...style,
      }}
    >
      {prefix}
      {value.toFixed(decimals)}
      {suffix}
    </span>
  );
};

/**
 * GlowText — Text with a subtle glow effect.
 */
export const GlowText: React.FC<{
  children: React.ReactNode;
  color?: string;
  glowColor?: string;
  style?: React.CSSProperties;
}> = ({ children, color = "#58a6ff", glowColor, style }) => {
  const glow = glowColor || color;
  return (
    <span
      style={{
        color,
        textShadow: `0 0 20px ${glow}40, 0 0 40px ${glow}20`,
        ...style,
      }}
    >
      {children}
    </span>
  );
};
