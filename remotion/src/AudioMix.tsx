import {
  Audio,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from "remotion";

/**
 * AudioMix — Full audio layer for the demo video v5.
 * Handles: BGM with ducking during narration, SFX at key moments.
 *
 * Scene timing (v5 — 10 scenes, MiMo TTS natural speed):
 *   01_title:        0-342    (11.4s)
 *   02_webui_home:   342-670  (10.9s)
 *   03_presets:      670-973  (10.1s)
 *   04_trace:        973-1173 (6.7s)
 *   05_cli:          1173-1483 (10.3s)
 *   06_verdict_ok:   1483-2007 (17.5s)
 *   07_verdict_no:   2007-2589 (19.4s)
 *   08_mcp_proof:    2589-2889 (10.0s)
 *   09_arch:         2889-3289 (13.3s)
 *   10_closing:      3289-3741 (15.1s)
 */

const NARRATION_WINDOWS: [number, number][] = [
  [0, 342],
  [342, 670],
  [670, 973],
  [973, 1173],
  [1483, 2007],
  [2007, 2589],
  [2589, 2889],
  [3100, 3400],
  [3450, 3741],
];

const isInNarration = (frame: number): boolean => {
  return NARRATION_WINDOWS.some(([s, e]) => frame >= s && frame < e);
};

const BgmLayer: React.FC = () => {
  const frame = useCurrentFrame();
  const baseVolume = 0.12;
  const duckVolume = 0.04;
  const targetVolume = isInNarration(frame) ? duckVolume : baseVolume;
  const volume = interpolate(frame, [0, 5], [0, targetVolume], {
    extrapolateRight: "clamp",
  });
  return <Audio src={staticFile("audio/bgm/ambient-tech-v2.mp3")} volume={volume} />;
};

export const AudioMix: React.FC = () => {
  return (
    <>
      {/* BGM — full duration with ducking */}
      <BgmLayer />

      {/* SFX: Whoosh for title scene entrance */}
      <Sequence from={5}>
        <Audio src={staticFile("audio/sfx/whoosh.mp3")} volume={0.25} />
      </Sequence>

      {/* SFX: Click for preset cards appearing */}
      <Sequence from={700}>
        <Audio src={staticFile("audio/sfx/click.mp3")} volume={0.3} />
      </Sequence>

      {/* SFX: Typing during CLI scene */}
      <Sequence from={1190} durationInFrames={100}>
        <Audio src={staticFile("audio/sfx/typing.mp3")} volume={0.3} />
      </Sequence>

      {/* SFX: Success when verdict is EXECUTABLE */}
      <Sequence from={1600}>
        <Audio src={staticFile("audio/sfx/success.mp3")} volume={0.5} />
      </Sequence>

      {/* SFX: Click for step cards in verdict scenes */}
      <Sequence from={1500}>
        <Audio src={staticFile("audio/sfx/click.mp3")} volume={0.25} />
      </Sequence>
      <Sequence from={1520}>
        <Audio src={staticFile("audio/sfx/click.mp3")} volume={0.2} />
      </Sequence>

      {/* SFX: Notification for REFUSED verdict */}
      <Sequence from={2200}>
        <Audio src={staticFile("audio/sfx/notification.mp3")} volume={0.4} />
      </Sequence>

      {/* SFX: Whoosh for MCP Proof scene */}
      <Sequence from={2590}>
        <Audio src={staticFile("audio/sfx/whoosh.mp3")} volume={0.25} />
      </Sequence>

      {/* SFX: Whoosh for architecture scene */}
      <Sequence from={2890}>
        <Audio src={staticFile("audio/sfx/whoosh.mp3")} volume={0.2} />
      </Sequence>
    </>
  );
};
