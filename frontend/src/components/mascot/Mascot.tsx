import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export type MascotPose = "idle" | "bob" | "aha" | "celebrate" | "slumped";

interface MascotProps {
  /** Expressive pose to render. */
  pose?: MascotPose;
  /** Size in pixels (applied to both width and height). Defaults to 56. */
  size?: number;
  className?: string;
}

function BucketBody() {
  return (
    <>
      <defs>
        <clipPath id="bc">
          <path d="M 10 32 Q 8 68 18 74 L 62 74 Q 72 68 70 32 Z" />
        </clipPath>
      </defs>
      <path d="M 10 32 Q 8 68 18 74 L 62 74 Q 72 68 70 32 Z" fill="white" />
      <rect x="10" y="30" width="11" height="46" fill="#CC2929" clipPath="url(#bc)" />
      <rect x="31" y="30" width="11" height="46" fill="#CC2929" clipPath="url(#bc)" />
      <rect x="52" y="30" width="11" height="46" fill="#CC2929" clipPath="url(#bc)" />
      <rect x="7" y="28" width="66" height="6" rx="3" fill="#B02020" />
    </>
  );
}

function Popcorn() {
  return (
    <>
      <circle cx="22" cy="22" r="7.5" fill="#F5D35E" />
      <circle cx="40" cy="17" r="9" fill="#F5D35E" />
      <circle cx="58" cy="22" r="7.5" fill="#F5D35E" />
      <circle cx="31" cy="16" r="6" fill="#EAC94A" />
      <circle cx="49" cy="16" r="6" fill="#EAC94A" />
    </>
  );
}

function EyesNormal() {
  return (
    <>
      <circle cx="32" cy="52" r="4.5" fill="#1a1a1c" />
      <circle cx="48" cy="52" r="4.5" fill="#1a1a1c" />
      <circle cx="33.5" cy="50.2" r="1.5" fill="white" />
      <circle cx="49.5" cy="50.2" r="1.5" fill="white" />
    </>
  );
}

function EyesWide() {
  return (
    <>
      <circle cx="32" cy="52" r="6" fill="#1a1a1c" />
      <circle cx="48" cy="52" r="6" fill="#1a1a1c" />
      <circle cx="34" cy="50" r="2" fill="white" />
      <circle cx="50" cy="50" r="2" fill="white" />
    </>
  );
}

function EyesSleepy() {
  return (
    <>
      <path d="M 27.5 54 Q 32 48 36.5 54 Z" fill="#1a1a1c" />
      <path d="M 43.5 54 Q 48 48 52.5 54 Z" fill="#1a1a1c" />
    </>
  );
}

function MouthSmile() {
  return <path d="M 30 62 Q 40 68 50 62" stroke="#1a1a1c" fill="none" strokeWidth="2" strokeLinecap="round" />;
}

function MouthGrin() {
  return <path d="M 28 61 Q 40 70 52 61" stroke="#1a1a1c" fill="none" strokeWidth="2.5" strokeLinecap="round" />;
}

function MouthSad() {
  return <path d="M 30 66 Q 40 60 50 66" stroke="#1a1a1c" fill="none" strokeWidth="2" strokeLinecap="round" />;
}

function ArmsIdle() {
  return (
    <>
      <path d="M 9 52 Q 3 45 5 37" stroke="#333" fill="none" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M 71 52 Q 77 45 75 37" stroke="#333" fill="none" strokeWidth="2.5" strokeLinecap="round" />
    </>
  );
}

function ArmsRaised() {
  return (
    <>
      <path d="M 9 50 Q 2 38 7 26" stroke="#333" fill="none" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M 71 50 Q 78 38 73 26" stroke="#333" fill="none" strokeWidth="2.5" strokeLinecap="round" />
    </>
  );
}

function ArmsHighRaised() {
  return (
    <>
      <path d="M 9 50 Q 0 34 6 20" stroke="#333" fill="none" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M 71 50 Q 80 34 74 20" stroke="#333" fill="none" strokeWidth="2.5" strokeLinecap="round" />
    </>
  );
}

function ArmsDown() {
  return (
    <>
      <path d="M 9 52 Q 4 60 8 68" stroke="#333" fill="none" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M 71 52 Q 76 60 72 68" stroke="#333" fill="none" strokeWidth="2.5" strokeLinecap="round" />
    </>
  );
}

function Sparkles() {
  return (
    <>
      <circle cx="6" cy="18" r="2" fill="#F5D35E" />
      <circle cx="74" cy="18" r="2" fill="#F5D35E" />
      <path d="M 6 12 L 6 24 M 0 18 L 12 18" stroke="#F5D35E" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M 74 12 L 74 24 M 68 18 L 80 18" stroke="#F5D35E" strokeWidth="1.5" strokeLinecap="round" />
    </>
  );
}

const BASE_SVG_PROPS = {
  viewBox: "0 0 80 90",
  xmlns: "http://www.w3.org/2000/svg",
  fill: "none",
} as const;

function IdleSvg() {
  return (
    <svg {...BASE_SVG_PROPS}>
      <Popcorn />
      <BucketBody />
      <EyesNormal />
      <MouthSmile />
      <ArmsIdle />
    </svg>
  );
}

function AhaSvg() {
  return (
    <svg {...BASE_SVG_PROPS}>
      <Popcorn />
      <BucketBody />
      <EyesWide />
      <MouthGrin />
      <ArmsRaised />
    </svg>
  );
}

function CelebrateSvg() {
  return (
    <svg {...BASE_SVG_PROPS}>
      <Sparkles />
      <Popcorn />
      <BucketBody />
      <EyesWide />
      <MouthGrin />
      <ArmsHighRaised />
    </svg>
  );
}

function SlumpedSvg() {
  return (
    <svg {...BASE_SVG_PROPS}>
      <Popcorn />
      <BucketBody />
      <EyesSleepy />
      <MouthSad />
      <ArmsDown />
    </svg>
  );
}

/**
 * Animated popcorn-bucket mascot. Poses range from idle to celebratory.
 *
 * "bob" is the same visual as "idle" with a continuous framer-motion
 * y-oscillation applied to signal that something is happening.
 *
 * @param pose - Expressive pose to render (default: "idle").
 * @param size - Render size in pixels (default: 56).
 * @param className - Optional wrapper classes.
 */
export function Mascot({ pose = "idle", size = 56, className }: MascotProps) {
  const isBob = pose === "bob";

  return (
    <motion.div
      className={cn("shrink-0 select-none", className)}
      style={{ width: size, height: size }}
      animate={isBob ? { y: [0, -6, 0] } : undefined}
      transition={isBob ? { duration: 1.4, repeat: Infinity, ease: "easeInOut" } : undefined}
    >
      {(pose === "idle" || pose === "bob") && <IdleSvg />}
      {pose === "aha" && <AhaSvg />}
      {pose === "celebrate" && <CelebrateSvg />}
      {pose === "slumped" && <SlumpedSvg />}
    </motion.div>
  );
}
