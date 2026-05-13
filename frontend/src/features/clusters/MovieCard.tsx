import { motion } from "framer-motion";
import type { MoviePublic } from "@/utils/types";
import { formatMovieSubtitle, formatRating } from "./utils/clusterFormatters";
import styles from "./styles/Reveal.module.css";

const POSTER_PLACEHOLDER =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 160 240'%3E%3Crect width='160' height='240' fill='%2318181b'/%3E%3C/svg%3E";

interface MovieCardProps {
  movie: MoviePublic;
  /** Animation stagger index. */
  index: number;
  /** Called when the card is clicked. */
  onClick: (movieId: number) => void;
}

/**
 * Film card with poster, title, year, genres, and rating.
 *
 * Staggers in on mount using Framer Motion. Hover scales the poster.
 * Clicking opens the detail modal.
 *
 * @param movie - MoviePublic data.
 * @param index - Used for staggered entrance delay.
 * @param onClick - Receives the movie id when clicked.
 * @returns An animated interactive film card.
 */
export function MovieCard({ movie, index, onClick }: MovieCardProps) {
  const subtitle = formatMovieSubtitle(movie.release_year, movie.genres);
  const rating = formatRating(movie.bayesian_rating ?? movie.vote_average);

  return (
    <motion.article
      className={styles.movieCard}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.06, 0.72), duration: 0.3, ease: "easeOut" }}
      onClick={() => onClick(movie.id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onClick(movie.id)}
      aria-label={`${movie.title}, ${movie.release_year ?? "year unknown"}`}
    >
      <div className={styles.posterWrapper}>
        <img
          src={movie.poster_url ?? POSTER_PLACEHOLDER}
          alt={`${movie.title} poster`}
          className={styles.poster}
          loading="lazy"
          onError={(e) => {
            (e.currentTarget as HTMLImageElement).src = POSTER_PLACEHOLDER;
          }}
        />
        <span className={styles.ratingPill}>{rating}</span>
      </div>
      <div className={styles.cardBody}>
        <p className={styles.movieTitle}>{movie.title}</p>
        <p className={styles.movieSubtitle}>{subtitle}</p>
      </div>
    </motion.article>
  );
}
