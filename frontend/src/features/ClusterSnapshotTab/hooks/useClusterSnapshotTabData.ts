import { useMemo } from 'react'
import { useConversation } from '@/features/Chat/hooks/useConversation'
import { useSyncConversationSnapshot } from '@/features/Chat/hooks/useSyncConversationSnapshot'
import { useClusterSnapshot } from './useClusterSnapshot'
import { useRootSnapshot } from './useRootSnapshot'
import { useScatterData } from './useScatterData'
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
	const { data: rootSnapshot } = useRootSnapshot()
	const hasConversation = !!conversationId
	const conversationSnapshotPending = hasConversation && (!!snapshotId ? snapshotLoading : !conversation)
	const isOnRootSnapshot = !!snapshotId && snapshotId === rootSnapshot?.id

	const snapshot = hasConversation
		? conversationSnapshot ?? (conversationSnapshotPending ? rootSnapshot : undefined)
		: rootSnapshot
	const dimmedAll = !hasConversation || conversationSnapshotPending || isOnRootSnapshot

	const { data: movieMap } = useExemplarMovies(snapshot)
	const scatterPoints = useScatterData(snapshot)

	const baseDomain = useMemo(() => {
		if (!rootSnapshot || rootSnapshot.members.length === 0) return undefined
		let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity
		for (const m of rootSnapshot.members) {
			if (m.umap_x < xMin) xMin = m.umap_x
			if (m.umap_x > xMax) xMax = m.umap_x
			if (m.umap_y < yMin) yMin = m.umap_y
			if (m.umap_y > yMax) yMax = m.umap_y
		}
		const xPad = (xMax - xMin) * 0.05 || 1
		const yPad = (yMax - yMin) * 0.05 || 1
		return {
			x: [xMin - xPad, xMax + xPad] as [number, number],
			y: [yMin - yPad, yMax + yPad] as [number, number],
		}
	}, [rootSnapshot])

	return {
		conversation,
		snapshotId,
		conversationSnapshot,
		rootSnapshot,
		movieMap,
		snapshot,
		hasConversation,
		conversationSnapshotPending,
		isOnRootSnapshot,
		dimmedAll,
		scatterPoints,
		baseDomain,
	}
}
