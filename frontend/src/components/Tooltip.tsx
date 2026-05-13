import type { ReactNode } from "react";
import styles from "../styles/Tooltip.module.css";

interface TooltipProps {
  /** Tooltip label text. */
  label: string;
  children: ReactNode;
}

/**
 * Simple CSS-only tooltip wrapper.
 *
 * @param label - Text displayed in the tooltip.
 * @param children - The element that triggers the tooltip on hover/focus.
 * @returns A wrapper that shows a tooltip above the child on hover.
 */
export function Tooltip({ label, children }: TooltipProps) {
  return (
    <span className={styles.wrapper} data-tooltip={label}>
      {children}
    </span>
  );
}
