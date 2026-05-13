import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Spinner } from "@/components/Spinner";
import { useSessionStore } from "@/store/sessionStore";
import { useUiStore } from "@/store/uiStore";
import { useFetchConvergedCluster } from "./hooks/useFetchConvergedCluster";
import { useRevealHandler } from "./hooks/useRevealHandler";
import { ConvergedClusterHeader } from "./ConvergedClusterHeader";
import { MovieGrid } from "./MovieGrid";
import { MovieDetailModal } from "./MovieDetailModal";
import styles from "./styles/Reveal.module.css";

/**
 * Full-bleed reveal panel shown after convergence.
 *
 * Fetches the converged cluster in a single round trip, plays the cinematic
 * entrance animation, then renders the cluster header and movie grid.
 * Mounts only when the session has converged.
 *
 * @param turnCount - Number of turns it took to converge (shown in the header).
 * @returns Animated reveal screen with cluster header, movie grid, and detail modal.
 */
export function RevealPanel({ turnCount }: { turnCount: number }) {
  const { sessionId } = useSessionStore();
  const { isRevealPlaying, finishReveal, selectedMovieId } = useUiStore();
  const { selectMovie, closeDetail } = useRevealHandler();
  const { data, isLoading } = useFetchConvergedCluster(sessionId, true);

  useEffect(() => {
    if (data && isRevealPlaying) {
      const timer = setTimeout(finishReveal, 1200);
      return () => clearTimeout(timer);
    }
  }, [data, isRevealPlaying, finishReveal]);

  if (isLoading) {
    return (
      <div className={styles.revealLoading}>
        <Spinner size={40} />
      </div>
    );
  }

  if (!data) return null;

  return (
    <>
      <AnimatePresence>
        {isRevealPlaying && (
          <motion.div
            className={styles.scrim}
            initial={{ y: "-100%" }}
            animate={{ y: "100%" }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.9, ease: [0.76, 0, 0.24, 1] }}
          />
        )}
      </AnimatePresence>

      <div className={styles.revealPanel}>
        <ConvergedClusterHeader cluster={data.cluster} turnCount={turnCount} />
        <MovieGrid movies={data.movies} onMovieClick={selectMovie} />
      </div>

      <MovieDetailModal movieId={selectedMovieId} onClose={closeDetail} />
    </>
  );
}
