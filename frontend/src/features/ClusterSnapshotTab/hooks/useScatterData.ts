import { useMemo } from 'react'
import type { ClusterSnapshotDto } from '@/api/dto/snapshots'

export interface ScatterPoint {
    movieId: number
    title: string
    clusterId: string | null
    clusterLabel: string | null
    x: number
    y: number
    probability: number
    isExemplar: boolean
}

/**
 * Derives scatter plot data points from a snapshot's pre-computed member list.
 * Each point carries its argmax probability (always-on opacity) and whether it
 * is an exemplar of any cluster (always-on size boost).
 *
 * @param snapshot - Active ClusterSnapshotDto (includes members with coords).
 * @returns Array of ScatterPoint objects ready for Recharts rendering.
 */
export function useScatterData(snapshot: ClusterSnapshotDto | undefined): ScatterPoint[] {
    return useMemo(() => {
        if (!snapshot) return []
        const labelByClusterId = new Map(snapshot.clusters.map((c) => [c.id, c.label]))

        const exemplarSet = new Set<number>()
        for (const cluster of snapshot.clusters) {
            for (const id of cluster.exemplar_movie_ids) exemplarSet.add(id)
        }

        return snapshot.members.map((m) => ({
            movieId: m.movie_id,
            title: m.title,
            clusterId: m.cluster_id,
            clusterLabel: labelByClusterId.get(m.cluster_id) ?? null,
            x: m.umap_x,
            y: m.umap_y,
            probability: m.probability,
            isExemplar: exemplarSet.has(m.movie_id),
        }))
    }, [snapshot])
}
