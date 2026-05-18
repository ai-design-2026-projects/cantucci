import { get } from "@/clients/apiClient";
import type { MovieDto } from "@/utils/types";

/**
 * Fetch full metadata for a single movie.
 *
 * @param movieId - TMDB integer movie id.
 * @returns MovieDto with all catalogue fields.
 */
export function fetchMovie(movieId: number): Promise<MovieDto> {
  return get<MovieDto>(`/movies/${movieId}`);
}
