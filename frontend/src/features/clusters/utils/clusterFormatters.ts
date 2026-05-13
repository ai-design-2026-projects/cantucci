/**
 * Build a full TMDB poster image URL from a relative path.
 *
 * @param posterPath - Relative path from the movies table (e.g. ``"/abc.jpg"``).
 * @returns Full URL, or null when posterPath is null/empty.
 */
export function buildPosterUrl(posterPath: string | null | undefined): string | null {
  if (!posterPath) return null;
  return `https://image.tmdb.org/t/p/w500${posterPath}`;
}

/**
 * Format a runtime in minutes as a human-readable string.
 *
 * @param minutes - Runtime in minutes, or null/undefined.
 * @returns E.g. ``"1h 52m"`` or ``"—"`` when not available.
 */
export function formatRuntime(minutes: number | null | undefined): string {
  if (!minutes) return "—";
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

/**
 * Format a vote_average rating to one decimal place.
 *
 * @param rating - Raw vote_average value (0–10), or null.
 * @returns E.g. ``"8.4"`` or ``"—"`` when not available.
 */
export function formatRating(rating: number | null | undefined): string {
  if (rating === null || rating === undefined) return "—";
  return rating.toFixed(1);
}

/**
 * Build a short subtitle line for a movie card.
 *
 * @param year - Release year or null.
 * @param genres - Array of genre names.
 * @returns E.g. ``"2019 · Drama, Horror"``.
 */
export function formatMovieSubtitle(year: number | null, genres: string[]): string {
  const parts: string[] = [];
  if (year) parts.push(String(year));
  if (genres.length > 0) parts.push(genres.slice(0, 2).join(", "));
  return parts.join(" · ") || "—";
}
