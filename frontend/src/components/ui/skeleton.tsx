import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/**
 * shadcn/ui Skeleton primitive.
 *
 * A subtle pulsing block used as a placeholder while real content loads.
 * Uses a low-contrast surface tint so it sits on dark backgrounds without
 * shouting. Pair with explicit width/height utilities.
 *
 * @param className - Tailwind utilities for size, shape, etc.
 * @param props - Standard div attributes.
 * @returns A pulsing placeholder element.
 */
export function Skeleton({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-white/[0.06]",
        className
      )}
      {...props}
    />
  );
}
