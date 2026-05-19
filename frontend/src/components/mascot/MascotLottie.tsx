import Lottie from "lottie-react";
import { cn } from "@/lib/utils";
import type { MascotPose } from "./Mascot";

import idleData from "./lottie/idle.json";
import bobData from "./lottie/bob.json";
import ahaData from "./lottie/aha.json";
import celebrateData from "./lottie/celebrate.json";
import slumpedData from "./lottie/slumped.json";
import thinkingData from "./lottie/thinking.json";

export type { MascotPose };

const POSE_DATA: Record<MascotPose | "thinking", object> = {
  idle: idleData,
  bob: bobData,
  aha: ahaData,
  celebrate: celebrateData,
  slumped: slumpedData,
  thinking: thinkingData,
};

interface MascotLottieProps {
  pose?: MascotPose | "thinking";
  size?: number;
  className?: string;
}

/**
 * Lottie-animated mascot. Accepts the same ``pose`` API as the SVG ``Mascot``
 * component plus the extra ``"thinking"`` pose (three-dot bounce) used in the
 * loading bubble. The animation JSON files in ``./lottie/`` are placeholder
 * animations — replace them with designer-authored files to upgrade fidelity
 * without touching any call-sites.
 *
 * @param pose - Expressive pose to play (default: "idle").
 * @param size - Render size in pixels (default: 56).
 * @param className - Optional wrapper classes.
 */
export function MascotLottie({ pose = "idle", size = 56, className }: MascotLottieProps) {
  return (
    <div
      className={cn("shrink-0 select-none", className)}
      style={{ width: size, height: size }}
    >
      <Lottie
        animationData={POSE_DATA[pose]}
        loop
        autoplay
        style={{ width: size, height: size }}
      />
    </div>
  );
}
