import type { ButtonHTMLAttributes } from "react";
import styles from "../styles/Button.module.css";

type Variant = "primary" | "secondary" | "ghost" | "choice";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visual variant. Defaults to "secondary". */
  variant?: Variant;
}

/**
 * Design-system button.
 *
 * @param variant - "primary" (gold), "secondary" (surface), "ghost" (outline), "choice" (ambiguity option).
 * @param children - Button label content.
 * @returns A styled button element.
 */
export function Button({ variant = "secondary", className, children, ...rest }: ButtonProps) {
  return (
    <button
      className={[styles.button, styles[variant], className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </button>
  );
}
