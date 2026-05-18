import { get } from "@/clients/apiClient";
import type { MoviePublic } from "@/utils/types";

/**
 * Fetch full metadata for a single movie.
 *
 * @param movieId - TMDB integer movie id.
 * @returns MoviePublic with all catalogue fields.
 */
export function fetchMovie(movieId: number): Promise<MoviePublic> {
  return get<MoviePublic>(`/movies/${movieId}`);
}
