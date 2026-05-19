import { motion } from "framer-motion";

interface ConfidenceBarProps {
  /** Score in [0, 1]. */
  score: number;
  /** Accessible label for screen readers. */
  label?: string;
}

function tierLabel(pct: number): string {
  if (pct < 40) return "Low";
  if (pct < 70) return "Med";
  return "High";
}

function tierFillClass(pct: number): string {
  if (pct < 40) return "bg-red-500";
  if (pct < 70) return "bg-amber-500";
  return "bg-emerald-500";
}

/**
 * Animated horizontal bar representing a soft-assignment confidence score.
 *
 * The bar fill is color-coded by tier: red (<40%), amber (40–70%), green (>70%).
 * A numeric percentage and tier label are shown to the right.
 *
 * @param score - Value in [0, 1] controlling bar fill width.
 * @param label - ARIA label prefix for the progress bar.
 * @returns An animated bar component using Framer Motion spring.
 */
export function ConfidenceBar({ score, label }: ConfidenceBarProps) {
  const pct = Math.round(Math.min(1, Math.max(0, score)) * 100);
  const tier = tierLabel(pct);
  const fillClass = tierFillClass(pct);

  return (
    <div className="flex items-center gap-2">
      <div
        className="relative h-2 w-72 shrink-0 rounded-full bg-muted"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ? `${label}: ${pct}% — ${tier}` : `${pct}% confidence — ${tier}`}
      >
        <motion.div
          className={`absolute inset-y-0 left-0 rounded-full ${fillClass}`}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ type: "spring", stiffness: 120, damping: 20 }}
        />
      </div>
      <span className="text-xs font-medium tabular-nums text-muted-foreground w-8 shrink-0 text-right">
        {pct}%
      </span>
      <span className="text-xs text-muted-foreground shrink-0 w-6">{tier}</span>
    </div>
  );
}
