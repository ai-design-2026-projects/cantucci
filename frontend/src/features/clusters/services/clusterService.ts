import { get } from "@/clients/apiClient";
import type { ConvergedClusterPublic, MoviePublic } from "@/utils/types";

/**
 * Fetch the converged cluster and its enriched movie list.
 *
 * @param sessionId - UUID of a converged session.
 * @returns ConvergedClusterPublic with cluster, movies, and preference_profile.
 */
export function fetchConvergedCluster(sessionId: string): Promise<ConvergedClusterPublic> {
  return get<ConvergedClusterPublic>(`/sessions/${sessionId}/converged-cluster`);
}

/**
 * Fetch full metadata for a single movie.
 *
 * @param movieId - TMDB integer movie id.
 * @returns MoviePublic with all catalogue fields.
 */
export function fetchMovie(movieId: number): Promise<MoviePublic> {
  return get<MoviePublic>(`/movies/${movieId}`);
}
