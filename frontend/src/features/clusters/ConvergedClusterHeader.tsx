import { motion } from "framer-motion";
import type { ClusterPublic } from "@/utils/types";
import styles from "./styles/Reveal.module.css";

interface ConvergedClusterHeaderProps {
  cluster: ClusterPublic;
  /** Number of turns it took to converge. */
  turnCount: number;
}

/**
 * Header shown at the top of the reveal screen after convergence.
 *
 * Slides up with a Framer Motion enter animation.
 *
 * @param cluster - The fine cluster that was selected.
 * @param turnCount - Number of turns to convergence (shown as a stat).
 * @returns Animated header with cluster name, description, and turn count.
 */
export function ConvergedClusterHeader({ cluster, turnCount }: ConvergedClusterHeaderProps) {
  return (
    <motion.header
      className={styles.clusterHeader}
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
    >
      <span className={styles.clusterEyebrow}>Your Cluster</span>
      <h1 className={styles.clusterName}>{cluster.name}</h1>
      {cluster.description && (
        <p className={styles.clusterDescription}>{cluster.description}</p>
      )}
      <p className={styles.convergenceStat}>
        Converged in <strong>{turnCount}</strong> {turnCount === 1 ? "turn" : "turns"}
      </p>
    </motion.header>
  );
}
