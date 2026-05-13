import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/Button";
import { Badge } from "@/components/Badge";
import { Spinner } from "@/components/Spinner";
import { useFetchMovieDetail } from "./hooks/useFetchMovieDetail";
import { formatRuntime, formatRating } from "./utils/clusterFormatters";
import styles from "./styles/Reveal.module.css";

const POSTER_PLACEHOLDER =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 160 240'%3E%3Crect width='160' height='240' fill='%2318181b'/%3E%3C/svg%3E";

interface MovieDetailModalProps {
  /** TMDB movie id to display, or null to hide the modal. */
  movieId: number | null;
  /** Called when the user closes the modal. */
  onClose: () => void;
}

/**
 * Full-detail modal for a single film.
 *
 * Fetches extended metadata via useFetchMovieDetail when movieId is set.
 * Closes on Escape key or backdrop click.
 *
 * @param movieId - TMDB id of the selected movie.
 * @param onClose - Callback to dismiss the modal.
 * @returns An AnimatePresence-wrapped modal dialog.
 */
export function MovieDetailModal({ movieId, onClose }: MovieDetailModalProps) {
  const isOpen = movieId !== null;
  const { data: movie, isLoading } = useFetchMovieDetail(movieId);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    if (isOpen) document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className={styles.modalBackdrop}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onClick={onClose}
          role="dialog"
          aria-modal="true"
          aria-label={movie?.title ?? "Film detail"}
        >
          <motion.div
            className={styles.modal}
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            onClick={(e) => e.stopPropagation()}
          >
            {isLoading && (
              <div className={styles.modalLoading}>
                <Spinner size={32} />
              </div>
            )}

            {movie && (
              <div className={styles.modalContent}>
                <img
                  src={movie.poster_url ?? POSTER_PLACEHOLDER}
                  alt={`${movie.title} poster`}
                  className={styles.modalPoster}
                  onError={(e) => {
                    (e.currentTarget as HTMLImageElement).src = POSTER_PLACEHOLDER;
                  }}
                />
                <div className={styles.modalBody}>
                  <h2 className={styles.modalTitle}>{movie.title}</h2>
                  <div className={styles.modalMeta}>
                    {movie.release_year && (
                      <Badge variant="dim">{movie.release_year}</Badge>
                    )}
                    {movie.runtime && (
                      <Badge variant="dim">{formatRuntime(movie.runtime)}</Badge>
                    )}
                    <Badge variant="gold">★ {formatRating(movie.bayesian_rating ?? movie.vote_average)}</Badge>
                  </div>

                  {movie.genres.length > 0 && (
                    <div className={styles.modalGenres}>
                      {movie.genres.map((g) => (
                        <Badge key={g} variant="default">{g}</Badge>
                      ))}
                    </div>
                  )}

                  {movie.overview && (
                    <p className={styles.modalOverview}>{movie.overview}</p>
                  )}

                  <div className={styles.modalCredits}>
                    {movie.director && (
                      <div className={styles.creditRow}>
                        <span className={styles.creditLabel}>Director</span>
                        <span>{movie.director}</span>
                      </div>
                    )}
                    {movie.top_cast.length > 0 && (
                      <div className={styles.creditRow}>
                        <span className={styles.creditLabel}>Cast</span>
                        <span>{movie.top_cast.join(", ")}</span>
                      </div>
                    )}
                  </div>

                  <Button variant="ghost" onClick={onClose} className={styles.modalClose}>
                    Close
                  </Button>
                </div>
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
