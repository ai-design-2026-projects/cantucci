import { useMemo } from 'react'
import { useConversation } from '@/features/Chat/hooks/useConversation'
import { useSyncConversationSnapshot } from '@/features/Chat/hooks/useSyncConversationSnapshot'
import { useClusterSnapshot } from './useClusterSnapshot'
import { useAllUmapPoints } from './useAllUmapPoints'
import { useScatterData, type ScatterPoint } from './useScatterData'
import { useExemplarMovies } from '@/features/ClustersInspect/hooks/useExemplarMovies'

/**
 * Collects the snapshot tab data, derived values, and query results.
 *
 * @param conversationId - Active conversation UUID, or undefined on the welcome screen.
 * @returns Snapshot data, derived scatter plot inputs, and loading flags.
 */
export function useClusterSnapshotTabData(conversationId: string | undefined) {
    const { data: conversation } = useConversation(conversationId)
    const snapshotId = conversation?.current_cluster_snapshot_id ?? null
    useSyncConversationSnapshot(snapshotId)

    const { data: conversationSnapshot, isLoading: snapshotLoading } = useClusterSnapshot(snapshotId)
    const { data: allUmapPoints } = useAllUmapPoints()
    const hasConversation = !!conversationId
    const conversationSnapshotPending = hasConversation && (!!snapshotId ? snapshotLoading : !conversation)
    const isUnclustered = hasConversation && !snapshotId && !!conversation

    const snapshot = hasConversation && !conversationSnapshotPending && !isUnclustered
        ? conversationSnapshot
        : undefined
    const dimmedAll = !hasConversation || conversationSnapshotPending || isUnclustered

    const { data: movieMap } = useExemplarMovies(snapshot)
    const clusteredPoints = useScatterData(snapshot)

    // Grey silhouette when no clustering is active (unclustered or welcome screen).
    const unclusteredPoints: ScatterPoint[] = useMemo(() => {
        if (!allUmapPoints) return []
        return allUmapPoints.map((p) => ({
            movieId: p.movie_id,
            title: p.title,
            clusterId: null,
            clusterLabel: null,
            colorSlot: null,
            x: p.umap_x,
            y: p.umap_y,
            probability: 1.0,
            isExemplar: false,
        }))
    }, [allUmapPoints])

    const scatterPoints = snapshot ? clusteredPoints : unclusteredPoints

    // Stable viewport bounds derived from all movies' coordinates.
    const baseDomain = useMemo(() => {
        const points = allUmapPoints ?? []
        if (points.length === 0) return undefined
        let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity
        for (const p of points) {
            if (p.umap_x < xMin) xMin = p.umap_x
            if (p.umap_x > xMax) xMax = p.umap_x
            if (p.umap_y < yMin) yMin = p.umap_y
            if (p.umap_y > yMax) yMax = p.umap_y
        }
        const xPad = (xMax - xMin) * 0.05 || 1
        const yPad = (yMax - yMin) * 0.05 || 1
        return {
            x: [xMin - xPad, xMax + xPad] as [number, number],
            y: [yMin - yPad, yMax + yPad] as [number, number],
        }
    }, [allUmapPoints])

    return {
        conversation,
        snapshotId,
        conversationSnapshot,
        movieMap,
        snapshot,
        hasConversation,
        conversationSnapshotPending,
        isUnclustered,
        dimmedAll,
        scatterPoints,
        baseDomain,
    }
}
