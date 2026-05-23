import { useQuery } from '@tanstack/react-query'
import { getMovieFetcher } from '@/api/services/movies'
import type { MovieDto } from '@/api/dto/movies'

/**
 * Fetch hook for loading full details of a single movie.
 * Used when opening the movie detail popup.
 *
 * @param movieId - TMDB integer ID, or null when no movie is selected.
 * @returns TanStack Query result wrapping MovieDto.
 */
export function useMovieDetails(movieId: number | null) {
	return useQuery<MovieDto>({
		queryKey: ['movie', movieId],
		queryFn: () => getMovieFetcher(movieId!),
		enabled: movieId !== null,
		staleTime: Infinity,
	})
}