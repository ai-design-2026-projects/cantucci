import { motion } from "framer-motion";

interface ConfidenceBarProps {
  /** Score in [0, 1]. */
  score: number;
  /** Accessible label for screen readers. */
  label?: string;
}

/**
 * Animated horizontal bar representing a soft-assignment confidence score.
 *
 * @param score - Value in [0, 1] controlling bar fill width.
 * @param label - ARIA label for the progress bar.
 * @returns An animated bar component using Framer Motion spring.
 */
export function ConfidenceBar({ score, label }: ConfidenceBarProps) {
  const pct = Math.round(Math.min(1, Math.max(0, score)) * 100);

  return (
    <div
      className="relative h-1.5 w-full overflow-hidden rounded-full bg-muted"
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label ?? `${pct}% confidence`}
    >
      <motion.div
        className="absolute inset-y-0 left-0 rounded-full bg-primary"
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ type: "spring", stiffness: 120, damping: 20 }}
      />
    </div>
  );
}
