import {
  Audio,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from "remotion";

/**
 * AudioMix — Full audio layer for the demo video v6.
 * Handles: BGM with ducking during narration, SFX at key moments.
 *
 * Scene timing (v6 — 9 scenes, MiMo TTS Dean speed=1.2):
 *   01_title:        0-150    (5s)
 *   02_webui_home:   150-390  (8s)
 *   03_presets:      390-600  (7s)
 *   04_cli:          600-810  (7s)
 *   05_verdict_ok:   810-1020 (7s)
 *   06_verdict_no:   1020-1230 (7s)
 *   07_mcp_proof:    1230-1440 (7s)
 *   08_arch:         1440-1650 (7s)
 *   09_closing:      1650-1860 (7s)
 */

const NARRATION_WINDOWS: [number, number][] = [
  [0, 150],
  [150, 390],
  [390, 600],
  [600, 810],
  [810, 1020],
  [1020, 1230],
  [1230, 1440],
  [1440, 1650],
  [1650, 1860],
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
      <Sequence from={400}>
        <Audio src={staticFile("audio/sfx/click.mp3")} volume={0.3} />
      </Sequence>

      {/* SFX: Typing during CLI scene */}
      <Sequence from={620} durationInFrames={80}>
        <Audio src={staticFile("audio/sfx/typing.mp3")} volume={0.3} />
      </Sequence>

      {/* SFX: Success when verdict is EXECUTABLE */}
      <Sequence from={900}>
        <Audio src={staticFile("audio/sfx/success.mp3")} volume={0.5} />
      </Sequence>

      {/* SFX: Click for step cards in verdict scenes */}
      <Sequence from={830}>
        <Audio src={staticFile("audio/sfx/click.mp3")} volume={0.25} />
      </Sequence>
      <Sequence from={850}>
        <Audio src={staticFile("audio/sfx/click.mp3")} volume={0.2} />
      </Sequence>

      {/* SFX: Notification for REFUSED verdict */}
      <Sequence from={1100}>
        <Audio src={staticFile("audio/sfx/notification.mp3")} volume={0.4} />
      </Sequence>

      {/* SFX: Whoosh for MCP Proof scene */}
      <Sequence from={1235}>
        <Audio src={staticFile("audio/sfx/whoosh.mp3")} volume={0.25} />
      </Sequence>

      {/* SFX: Whoosh for architecture scene */}
      <Sequence from={1445}>
        <Audio src={staticFile("audio/sfx/whoosh.mp3")} volume={0.2} />
      </Sequence>
    </>
  );
};
