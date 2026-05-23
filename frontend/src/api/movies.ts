import { apiClient } from './client'

export interface MovieDto {
  id: number
  title: string
  release_year: number | null
  runtime: number | null
  vote_average: number | null
  vote_count: number | null
  bayesian_rating: number | null
  overview: string | null
  poster_url: string | null
  genres: string[]
  director: string | null
  top_cast: string[]
  original_language: string | null
  trailer_youtube_key: string | null
  umap_x: number | null
  umap_y: number | null
}

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
