import { MovieCard } from "./MovieCard";
import type { MoviePublic } from "@/utils/types";
import styles from "./styles/Reveal.module.css";

interface MovieGridProps {
  movies: MoviePublic[];
  /** Called when a card is clicked; receives the movie id. */
  onMovieClick: (movieId: number) => void;
}

/**
 * Responsive grid of MovieCard components.
 *
 * @param movies - Ordered list of movies to display (top 20 by score).
 * @param onMovieClick - Callback for card selection.
 * @returns A responsive grid of animated film cards.
 */
export function MovieGrid({ movies, onMovieClick }: MovieGridProps) {
  if (movies.length === 0) {
    return (
      <p className={styles.emptyGrid}>
        No movies available yet — the Cluster Agent is still being implemented.
      </p>
    );
  }

  return (
    <div className={styles.movieGrid}>
      {movies.map((movie, i) => (
        <MovieCard
          key={movie.id}
          movie={movie}
          index={i}
          onClick={onMovieClick}
        />
      ))}
    </div>
  );
}
