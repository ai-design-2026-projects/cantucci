import { useQuery } from "@tanstack/react-query";
import { fetchMovie } from "@/features/clusters/services/clusterService";
import type { MovieDto } from "@/utils/types";

/**
 * Fetch extended metadata for a single movie.
 *
 * Only fires when movieId is non-null (i.e. a card is clicked).
 *
 * @param movieId - TMDB movie id, or null when no movie is selected.
 * @returns TanStack Query result with MovieDto.
 */
export function useFetchMovieDetail(movieId: number | null) {
  return useQuery<MovieDto, Error>({
    queryKey: ["movie", movieId],
    queryFn: () => fetchMovie(movieId!),
    enabled: movieId !== null,
    staleTime: Infinity,
  });
}
