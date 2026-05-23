import { useMemo } from 'react'
import type { ClusterSnapshotDto } from '@/api/dto/snapshots'
import type { MovieDto } from '@/api/dto/movies'

export interface ScatterPoint {
	movieId: number
	title: string
	clusterId: string
	clusterLabel: string | null
	x: number
	y: number
}

/**
 * Derives scatter plot data points from a snapshot and its enriched movie map.
 * Filters out exemplars without UMAP coordinates. Marks each point with its
 * cluster ID for color coding.
 *
 * @param snapshot  - Active ClusterSnapshotDto.
 * @param movieMap  - Map of movie ID to MovieDto including umap_x/umap_y.
 * @returns Array of ScatterPoint objects ready for Recharts rendering.
 */
export function useScatterData(
	snapshot: ClusterSnapshotDto | undefined,
	movieMap: Map<number, MovieDto> | undefined,
): ScatterPoint[] {
	return useMemo(() => {
		if (!snapshot || !movieMap) return []
		const points: ScatterPoint[] = []
		for (const cluster of snapshot.clusters) {
			for (const movieId of cluster.exemplar_movie_ids) {
				const movie = movieMap.get(movieId)
				if (!movie || movie.umap_x == null || movie.umap_y == null) continue
				points.push({
					movieId: movie.id,
					title: movie.title,
					clusterId: cluster.id,
					clusterLabel: cluster.label,
					x: movie.umap_x,
					y: movie.umap_y,
				})
			}
		}
		return points
	}, [snapshot, movieMap])
}
