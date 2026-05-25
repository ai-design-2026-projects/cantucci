import { useMemo } from 'react'
import type { ClusterSnapshotDto } from '@/api/dto/snapshots'

export interface ScatterPoint {
	movieId: number
	title: string
	clusterId: string | null
	clusterLabel: string | null
	x: number
	y: number
}

/**
 * Derives scatter plot data points from a snapshot's pre-computed member list.
 * Each point carries its argmax cluster ID for color coding. Points whose
 * cluster label comes from the snapshot's cluster list are enriched inline.
 *
 * @param snapshot - Active ClusterSnapshotDto (includes members with coords).
 * @returns Array of ScatterPoint objects ready for Recharts rendering.
 */
export function useScatterData(snapshot: ClusterSnapshotDto | undefined): ScatterPoint[] {
	return useMemo(() => {
		if (!snapshot) return []
		const labelByClusterId = new Map(snapshot.clusters.map((c) => [c.id, c.label]))
		return snapshot.members.map((m) => ({
			movieId: m.movie_id,
			title: m.title,
			clusterId: m.cluster_id,
			clusterLabel: labelByClusterId.get(m.cluster_id) ?? null,
			x: m.umap_x,
			y: m.umap_y,
		}))
	}, [snapshot])
}
