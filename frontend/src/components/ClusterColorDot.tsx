import styles from "../styles/ClusterColorDot.module.css";

/** Hue seeds per cluster index, cycling if more than 6 clusters. */
const CLUSTER_HUES = [220, 160, 40, 280, 15, 190];

interface ClusterColorDotProps {
  /** 0-based index of the cluster, used to pick a hue. */
  index: number;
  /** Diameter in pixels. Defaults to 10. */
  size?: number;
}

/**
 * Small filled circle with a per-cluster colour derived from its index.
 *
 * @param index - Cluster order index, used to derive the dot hue.
 * @param size - Diameter in pixels.
 * @returns A coloured dot span.
 */
export function ClusterColorDot({ index, size = 10 }: ClusterColorDotProps) {
  const hue = CLUSTER_HUES[index % CLUSTER_HUES.length];
  return (
    <span
      className={styles.dot}
      style={{
        width: size,
        height: size,
        background: `hsl(${hue}, 60%, 55%)`,
      }}
      aria-hidden="true"
    />
  );
}
