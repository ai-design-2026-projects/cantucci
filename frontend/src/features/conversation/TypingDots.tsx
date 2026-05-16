import { cn } from "@/lib/utils";

interface TypingDotsProps {
  /** Optional Tailwind classes to extend the wrapper (e.g. spacing). */
  className?: string;
}

/**
 * Three pulsing dots used as a typing-style waiting indicator.
 *
 * Each dot animates on a staggered delay so the row reads as a wave.
 * The animation respects ``prefers-reduced-motion`` via Tailwind's motion-safe
 * variant: when motion is reduced, dots are shown statically at low opacity.
 *
 * @param className - Optional wrapper classes.
 * @returns An inline-flex span of three dots.
 */
export function TypingDots({ className }: TypingDotsProps) {
  return (
    <span
      className={cn("inline-flex items-end gap-1.5", className)}
      aria-hidden="true"
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="block h-1.5 w-1.5 rounded-full bg-gold opacity-40 motion-safe:animate-dot-pulse"
          style={{ animationDelay: `${i * 0.16}s` }}
        />
      ))}
    </span>
  );
}
