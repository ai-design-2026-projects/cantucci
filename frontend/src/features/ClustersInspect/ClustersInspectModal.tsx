import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/dialog'
import { TooltipProvider } from '@/components/tooltip'
import { clusterColorFromUuid, clusterColorKey } from '@/styles/theme'
import { useThemeStore } from '@/store/useThemeStore'
import type { ClusterSnapshotDto } from '@/api/dto/snapshots'
import type { MovieDto } from '@/api/dto/movies'
import { ClusterInspectCard } from './components/ClusterInspectCard'

/**
 * Modal popup showing all clusters in the active snapshot as rich cards.
 * When no snapshot is provided (grey-dot / pre-clustering mode), shows an
 * empty-state message instead. Each card has a color stripe, title, description,
 * and exemplar thumbnails.
 *
 * @param open         - Whether the dialog is visible.
 * @param onClose      - Handler to dismiss the dialog.
 * @param snapshot     - Active cluster snapshot, or undefined if no clustering has been done.
 * @param movieMap     - Map from movie ID to MovieDto (pre-fetched by parent).
 * @param onMovieClick - Opens the movie detail popup for a given movie ID.
 * @returns Centered dialog with scrollable cluster card list or empty-state message.
 */
export function ClusterInspectModal({
	open,
	onClose,
	snapshot,
	movieMap,
	onMovieClick,
}: {
	open: boolean
	onClose: () => void
	snapshot: ClusterSnapshotDto | undefined
	movieMap: Map<number, MovieDto>
	onMovieClick: (movieId: number) => void
}) {
	const isDark = useThemeStore((s) => s.theme === 'dark')

	return (
		<Dialog open={open} onOpenChange={(v) => !v && onClose()}>
			<DialogContent className="max-w-3xl w-[90vw] max-h-[85vh] p-0 flex flex-col">
				<DialogHeader className="px-6 pt-5 pb-3 border-b border-[var(--color-border)]">
					<DialogTitle>Clusters</DialogTitle>
					{snapshot && (
						<p className="text-xs text-[var(--color-muted)] mt-0.5">
							{snapshot.clusters.length} cluster{snapshot.clusters.length !== 1 ? 's' : ''}
						</p>
					)}
				</DialogHeader>
				{snapshot ? (
					<TooltipProvider delayDuration={300}>
						<div className="flex-1 overflow-y-auto scrollbar-styled px-6 py-4 space-y-3">
							{snapshot.clusters.map((cluster) => (
								<ClusterInspectCard
									key={cluster.id}
									cluster={cluster}
									color={clusterColorFromUuid(clusterColorKey(snapshot.operation, cluster), isDark)}
									movieMap={movieMap}
									onMovieClick={onMovieClick}
								/>
							))}
						</div>
					</TooltipProvider>
				) : (
					<div className="flex-1 flex items-center justify-center text-sm text-[var(--color-muted)] px-6 py-8">
						No clustering performed yet — start a conversation to build clusters.
					</div>
				)}
			</DialogContent>
		</Dialog>
	)
}
