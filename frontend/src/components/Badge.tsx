import type { ReactNode } from "react";
import styles from "../styles/Badge.module.css";

type BadgeVariant = "default" | "gold" | "blue" | "dim";

interface BadgeProps {
  children: ReactNode;
  /** Visual variant. Defaults to "default". */
  variant?: BadgeVariant;
}

/**
 * Small inline label badge.
 *
 * @param variant - Colour variant: "default", "gold", "blue", "dim".
 * @param children - Badge text content.
 * @returns A styled span badge.
 */
export function Badge({ children, variant = "default" }: BadgeProps) {
  return (
    <span className={[styles.badge, styles[variant]].join(" ")}>
      {children}
    </span>
  );
}
