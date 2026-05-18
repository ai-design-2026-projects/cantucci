/**
 * Return the poster URL as-is.
 *
 * The backend already returns a full TMDB URL in ``poster_url``
 * (``https://image.tmdb.org/t/p/w500{path}``). This function is kept as a
 * passthrough so call sites don't need to change.
 *
 * @param posterUrl - Full poster URL from the backend, or null/undefined.
 * @returns The URL unchanged, or null when absent.
 */
export function buildPosterUrl(posterUrl: string | null | undefined): string | null {
  return posterUrl ?? null;
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

/**
 * Derive a deterministic HSL color from a cluster UUID.
 *
 * Hue varies across 0–359; saturation and lightness are fixed so all cluster
 * colours feel tonally consistent regardless of how many clusters exist.
 *
 * @param id - Cluster UUID string.
 * @returns CSS HSL color string, e.g. ``"hsl(127 55% 50%)"``.
 */
export function clusterColor(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  }
  const hue = hash % 360;
  return `hsl(${hue} 55% 50%)`;
}
