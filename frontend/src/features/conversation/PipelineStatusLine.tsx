import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/utils";

/**
 * A pipeline stage shown to the oracle during a turn wait.
 *
 * ``startSeconds`` is the elapsed-second threshold at which this stage
 * becomes active. Variants rotate within an active stage on a fixed cadence
 * so the copy feels alive without claiming false precision.
 */
export interface PipelineStage {
  /** Stable identifier — also used as the React key for the active stage. */
  id: string;
  /** Elapsed seconds at which this stage takes over (inclusive). */
  startSeconds: number;
  /** Lines rotated through while this stage is active. */
  variants: readonly string[];
}

/**
 * Product-soft pipeline stages, time-mapped to the typical turn latency
 * (Retrieval → Clustering → Decision → Ambiguity). Exposed for tests.
 */
export const STAGES: readonly PipelineStage[] = [
  {
    id: "retrieval",
    startSeconds: 0,
    variants: [
      "Finding films you might love…",
      "Pulling candidates from the catalogue…",
      "Reading between the lines…",
    ],
  },
  {
    id: "clustering",
    startSeconds: 7,
    variants: [
      "Grouping by mood…",
      "Looking for patterns…",
      "Sorting the shortlist…",
    ],
  },
  {
    id: "decision",
    startSeconds: 18,
    variants: [
      "Picking the best slate…",
      "Weighing the options…",
      "Choosing what to ask next…",
    ],
  },
  {
    id: "ambiguity",
    startSeconds: 28,
    variants: [
      "Checking the close calls…",
      "Probing edge cases…",
      "Almost there…",
    ],
  },
] as const;

/** How often (ms) the variant rotates within an active stage. */
const VARIANT_TICK_MS = 3000;

/**
 * Select the active stage for a given elapsed-seconds value.
 *
 * Picks the last stage whose ``startSeconds`` is <= elapsed.
 *
 * @param elapsedSeconds - Seconds since the wait started.
 * @param stages - Stage table, ordered by ``startSeconds`` ascending.
 * @returns The currently-active stage.
 */
export function selectStage(
  elapsedSeconds: number,
  stages: readonly PipelineStage[] = STAGES,
): PipelineStage {
  let active = stages[0];
  for (const s of stages) {
    if (elapsedSeconds >= s.startSeconds) active = s;
  }
  return active;
}

interface PipelineStatusLineProps {
  /** Override the stages (used in tests). */
  stages?: readonly PipelineStage[];
  /** Override the variant rotation cadence in ms (used in tests). */
  tickMs?: number;
  /** Optional Tailwind classes for the wrapper. */
  className?: string;
}

/**
 * A single line of product-soft status copy that advances through pipeline
 * stages over time and rotates through variant phrasings within a stage.
 *
 * Self-clocking: starts its internal timer on mount and stops when unmounted.
 * No props are required in production — the assistant bubble simply mounts
 * this component while ``assistant_message`` is empty and unmounts it once
 * the real reply arrives.
 *
 * Uses framer-motion ``AnimatePresence`` for a soft crossfade between lines.
 *
 * @param stages - Override stages for tests.
 * @param tickMs - Override variant cadence for tests.
 * @param className - Optional wrapper classes.
 * @returns A status line element.
 */
export function PipelineStatusLine({
  stages = STAGES,
  tickMs = VARIANT_TICK_MS,
  className,
}: PipelineStatusLineProps) {
  const [elapsed, setElapsed] = useState(0);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const id = window.setInterval(() => {
      setElapsed((Date.now() - start) / 1000);
      setTick((t) => t + 1);
    }, tickMs);
    return () => window.clearInterval(id);
  }, [tickMs]);

  const stage = selectStage(elapsed, stages);
  const variant = stage.variants[tick % stage.variants.length];
  const lineKey = `${stage.id}:${tick % stage.variants.length}`;

  return (
    <span
      className={cn("block min-h-[1.2em] text-sm text-text-secondary", className)}
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={lineKey}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.35, ease: "easeOut" }}
          className="inline-block"
        >
          {variant}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}
