import styles from "../styles/Spinner.module.css";

interface SpinnerProps {
  /** Size in pixels. Defaults to 20. */
  size?: number;
}

/**
 * Animated loading indicator.
 *
 * @param size - Diameter in pixels.
 * @returns A CSS-animated circular spinner.
 */
export function Spinner({ size = 20 }: SpinnerProps) {
  return (
    <span
      className={styles.spinner}
      style={{ width: size, height: size }}
      aria-label="Loading"
      role="status"
    />
  );
}
