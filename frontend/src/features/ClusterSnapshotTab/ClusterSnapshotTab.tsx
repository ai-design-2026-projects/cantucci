import { useState, useMemo } from 'react'
import { useSnapshotStore } from '@/store/useSnapshotStore'
import { useConversation } from '@/features/Chat/hooks/useConversation'
import { useSyncConversationSnapshot } from '@/features/Chat/hooks/useSyncConversationSnapshot'
import { useClusterSnapshot } from './hooks/useClusterSnapshot'
import { useRootSnapshot } from './hooks/useRootSnapshot'
import { useScatterData } from './hooks/useScatterData'
import { SnapshotPlot } from './components/SnapshotPlot'
import { EvolutionMapButton } from '@/features/ClusterSnapshotTab/components/EvolutionMapButton'
import { EvolutionMapModal } from '@/features/EvolutionMap/EvolutionMapModal'
import { InspectButton } from '@/features/ClusterInspect/components/InspectButton'
import { ClusterInspectModal } from '@/features/ClusterInspect/ClusterInspectModal'
import { MoviePopup } from '@/features/ClusterInspect/components/MoviePopup'
import { useExemplarMovies } from '@/features/ClusterInspect/hooks/useExemplarMovies'

interface ClusterSnapshotTabProps {
	conversationId: string | undefined
}

/**
 * Fixed right-panel showing the scatter plot of the active cluster snapshot.
 * When no conversation is active, displays a grey silhouette of all movies
 * using the base HDBSCAN snapshot. Owns the Evolution Map and Inspect modal state.
 *
 * @param conversationId - Active conversation UUID, or undefined when on the welcome screen.
 * @returns Right-panel content with header, scatter plot, and movie popup.
 */
export function ClusterSnapshotTab({ conversationId }: ClusterSnapshotTabProps) {
	const { selectedClusterId } = useSnapshotStore()
	const [selectedMovieId, setSelectedMovieId] = useState<number | null>(null)
	const [evolutionOpen, setEvolutionOpen] = useState(false)
	const [inspectOpen, setInspectOpen] = useState(false)

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
	const scatterPoints = useScatterData(snapshot, movieMap)

	const baseDomain = useMemo(() => {
		if (!rootSnapshot) return undefined
		const exemplarIds = rootSnapshot.clusters.flatMap((c) => c.exemplar_movie_ids)
		const xs: number[] = []
		const ys: number[] = []
		for (const id of exemplarIds) {
			const movie = movieMap?.get(id)
			if (movie?.umap_x != null && movie?.umap_y != null) {
				xs.push(movie.umap_x)
				ys.push(movie.umap_y)
			}
		}
		if (xs.length === 0) return undefined
		const xMin = Math.min(...xs)
		const xMax = Math.max(...xs)
		const yMin = Math.min(...ys)
		const yMax = Math.max(...ys)
		const xPad = (xMax - xMin) * 0.05 || 1
		const yPad = (yMax - yMin) * 0.05 || 1
		return {
			x: [xMin - xPad, xMax + xPad] as [number, number],
			y: [yMin - yPad, yMax + yPad] as [number, number],
		}
	}, [rootSnapshot, movieMap])

	return (
		<div className="flex flex-col h-full w-full">
			<div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--color-border)] flex-shrink-0">
				<span className="text-sm font-medium text-[var(--color-text)]">Cluster Snapshot</span>
				<div className="flex items-center gap-1">
					<InspectButton onClick={() => setInspectOpen(true)} disabled={!conversationSnapshot} />
					<EvolutionMapButton onClick={() => setEvolutionOpen(true)} disabled={!conversationId} />
				</div>
			</div>

			<div className="flex-1 min-h-0 relative">
				{snapshot ? (
					<SnapshotPlot
						points={scatterPoints}
						snapshot={snapshot}
						selectedClusterId={selectedClusterId}
						onPointClick={setSelectedMovieId}
						dimmedAll={dimmedAll}
						baseDomain={baseDomain}
					/>
				) : (
					<div className="h-full flex items-center justify-center text-sm text-[var(--color-muted)]">
						No snapshot data yet
					</div>
				)}
			</div>

			{conversationId && (
				<>
					<MoviePopup
						movieId={selectedMovieId}
						snapshot={conversationSnapshot}
						onClose={() => setSelectedMovieId(null)}
					/>
					<EvolutionMapModal
						open={evolutionOpen}
						onClose={() => setEvolutionOpen(false)}
						conversationId={conversationId}
					/>
					{conversationSnapshot && (
						<ClusterInspectModal
							open={inspectOpen}
							onClose={() => setInspectOpen(false)}
							snapshot={conversationSnapshot}
							movieMap={movieMap ?? new Map()}
							onMovieClick={(id) => setSelectedMovieId(id)}
						/>
					)}
				</>
			)}
		</div>
	)
}
