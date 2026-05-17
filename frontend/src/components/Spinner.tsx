import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface SpinnerProps {
  /** Size in pixels. Defaults to 20. */
  size?: number;
  className?: string;
}

/**
 * Animated loading indicator using lucide-react Loader2 icon.
 *
 * @param size - Diameter in pixels.
 * @param className - Optional Tailwind classes.
 * @returns A spinning loader icon.
 */
export function Spinner({ size = 20, className }: SpinnerProps) {
  return (
    <Loader2
      className={cn("animate-spin text-muted-foreground", className)}
      style={{ width: size, height: size }}
      aria-label="Loading"
      role="status"
    />
  );
}
