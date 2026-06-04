import { apiClient } from '../client'
import type { MovieDto } from '../dto/movies'

/**
 * Fetch full metadata for a single movie.
 *
 * @param movieId - TMDB integer movie ID.
 * @returns MovieDto on success.
 */
export async function getMovieFetcher(movieId: number): Promise<MovieDto> {
    return apiClient<MovieDto>(`/movies/${movieId}`)
}

/**
 * Fetch full metadata for a batch of movies in a single request.
 * Unknown IDs are silently omitted from the response.
 *
 * @param ids - Up to 200 TMDB integer movie IDs.
 * @returns Array of MovieDto in the same order as ids (missing IDs dropped).
 */
export async function getMoviesBatchFetcher(ids: number[]): Promise<MovieDto[]> {
    if (ids.length === 0) return []
    return apiClient<MovieDto[]>('/movies/batch', {
        method: 'POST',
        body: JSON.stringify({ ids }),
    })
}
