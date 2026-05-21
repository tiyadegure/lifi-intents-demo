import { Composition } from "remotion";
import { Demo } from "./Demo";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="LifiIntentsDemo"
      component={Demo}
      durationInFrames={2100}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{}}
    />
  );
};
