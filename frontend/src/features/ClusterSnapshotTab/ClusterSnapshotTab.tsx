import { useClusterSnapshotTabData } from './hooks/useClusterSnapshotTabData'
import { useClusterSnapshotTabHandlers } from './hooks/useClusterSnapshotTabHandlers'
import { useSnapshotStore } from '@/store/useSnapshotStore'
import { SnapshotPlot } from './components/SnapshotPlot'
import { EvolutionMapButton } from './components/EvolutionMapButton'
import { EvolutionMapModal } from '@/features/EvolutionMap/EvolutionMapModal'
import { InspectButton } from '@/features/ClustersInspect/components/InspectButton'
import { ClusterInspectModal } from '@/features/ClustersInspect/ClustersInspectModal'
import { MoviePopup } from '@/features/ClustersInspect/components/MoviePopup'

/**
 * Fixed right-panel showing the scatter plot of the active cluster snapshot.
 * When no conversation is active, displays a grey silhouette of all movies
 * using the base HDBSCAN snapshot. Owns the Evolution Map and Inspect modal state.
 *
 * @param conversationId - Active conversation UUID, or undefined when on the welcome screen.
 * @returns Right-panel content with header, scatter plot, and movie popup.
 */

export function ClusterSnapshotTab({ conversationId }: { conversationId: string | undefined }) {
	const { selectedClusterId } = useSnapshotStore()
	const {
		conversationSnapshot,
		movieMap,
		snapshot,
		dimmedAll,
		scatterPoints,
		baseDomain,
	} = useClusterSnapshotTabData(conversationId)
	const {
		selectedMovieId,
		setSelectedMovieId,
		evolutionOpen,
		setEvolutionOpen,
		inspectOpen,
		setInspectOpen,
	} = useClusterSnapshotTabHandlers()

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
							onMovieClick={(id: number) => setSelectedMovieId(id)}
						/>
					)}
				</>
			)}
		</div>
	)
}
