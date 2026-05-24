import { useQuery } from '@tanstack/react-query'
import { getMoviesBatchFetcher } from '@/api/services/movies'
import type { ClusterSnapshotDto } from '@/api/dto/snapshots'
import type { MovieDto } from '@/api/dto/movies'

/**
 * Fetch hook that collects all exemplar_movie_ids from a snapshot's clusters
 * and requests them in a single batch call.
 *
 * @param snapshot - ClusterSnapshotDto whose clusters provide the exemplar IDs.
 * @returns TanStack Query result wrapping a Map from movie ID to MovieDto.
 */
export function useExemplarMovies(snapshot: ClusterSnapshotDto | undefined) {
	const allIds = snapshot
		? snapshot.clusters.flatMap((c) => c.exemplar_movie_ids)
		: []
	const uniqueIds = [...new Set(allIds)]

	return useQuery<Map<number, MovieDto>>({
		queryKey: ['exemplar-movies', snapshot?.id, uniqueIds.join(',')],
		queryFn: async () => {
			const movies = await getMoviesBatchFetcher(uniqueIds)
			const map = new Map<number, MovieDto>()
			for (const m of movies) map.set(m.id, m)
			return map
		},
		enabled: uniqueIds.length > 0,
		staleTime: 5 * 60_000,
	})
}