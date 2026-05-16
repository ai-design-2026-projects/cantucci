import { AnimatePresence, motion } from "framer-motion";
import { useUiStore } from "@/store/uiStore";
import { cn } from "@/lib/utils";
import type { ProgressStep } from "@/features/conversation/services/turnService";

/**
 * A pipeline stage shown to the oracle during a turn wait.
 *
 * Keyed by the backend ``ProgressStep`` so the UI advances when real progress
 * events arrive on the NDJSON stream instead of on a hardcoded timer.
 */
export interface PipelineStage {
  /** Stable identifier; matches a backend ``ProgressStep`` value. */
  id: ProgressStep;
  /** Product-soft copy shown while this step is active. */
  label: string;
}

/**
 * Product-soft copy for each pipeline step the backend reports. The values
 * mirror ``backend/orchestrator/progress.py::ProgressStep``; whenever a new
 * step is added there, add a matching row here.
 */
export const STAGES: Readonly<Record<ProgressStep, PipelineStage>> = {
  retrieval: { id: "retrieval", label: "Finding films you might love…" },
  cluster:   { id: "cluster",   label: "Grouping by mood…" },
  decision:  { id: "decision",  label: "Picking the best slate…" },
  ambiguity: { id: "ambiguity", label: "Checking the close calls…" },
  render:    { id: "render",    label: "Writing the recommendation…" },
  persist:   { id: "persist",   label: "Saving your turn…" },
} as const;

/**
 * Fallback shown before the first progress event arrives (or when the backend
 * is running on the legacy code path without progress callbacks).
 */
const INITIAL_LABEL = STAGES.retrieval.label;

interface PipelineStatusLineProps {
  /**
   * Override the active step for tests or storybook. When provided, the
   * component ignores ``useUiStore.currentStep``.
   */
  step?: ProgressStep | null;
  /** Optional Tailwind classes for the wrapper. */
  className?: string;
}

/**
 * Single status line driven by the backend's streamed pipeline step.
 *
 * Reads ``currentStep`` from ``useUiStore`` (set by ``useTurnHandler`` on
 * every NDJSON ``progress`` event) and maps it to product-soft copy via the
 * ``STAGES`` table. Before the first event arrives, falls back to the
 * retrieval-stage label so the placeholder never appears empty.
 *
 * Uses framer-motion ``AnimatePresence`` for a soft crossfade when the step
 * changes — the right primitive for event-driven transitions because the key
 * change is what triggers the animation, not elapsed time.
 *
 * @param step - Override the active step (used in tests).
 * @param className - Optional wrapper classes.
 * @returns A status line element.
 */
export function PipelineStatusLine({ step, className }: PipelineStatusLineProps = {}) {
  const storeStep = useUiStore((s) => s.currentStep);
  const active = step !== undefined ? step : storeStep;
  const stage = active ? STAGES[active] : null;
  const label = stage?.label ?? INITIAL_LABEL;
  const lineKey = stage?.id ?? "initial";

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
          {label}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}
