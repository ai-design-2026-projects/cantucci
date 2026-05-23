import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/dialog'
import { Badge } from '@/components/badge'
import { useMovieDetails } from '../hooks/useMovieDetails'
import { clusterColorFromUuid } from '@/styles/theme'
import { useThemeStore } from '@/store/useThemeStore'
import type { ClusterSnapshotDto } from '@/api/dto/snapshots'

/**
 * Movie detail dialog showing poster, overview, metadata, and trailer.
 * When the movie is an exemplar of a cluster in the active snapshot, a
 * colored cluster chip appears below the title.
 *
 * @param movieId  - TMDB ID of the movie to display, or null when closed.
 * @param snapshot - Active snapshot used to identify which cluster this movie belongs to.
 * @param onClose  - Called when the dialog is dismissed.
 * @returns Radix Dialog with full movie metadata.
 */
export function MoviePopup({
	movieId,
	snapshot,
	onClose,
}: {
	movieId: number | null
	snapshot: ClusterSnapshotDto | undefined
	onClose: () => void
}) {
	const { data: movie, isLoading } = useMovieDetails(movieId)
	const isDark = useThemeStore((s) => s.theme === 'dark')

	const matchedCluster = snapshot?.clusters.find((c) =>
		c.exemplar_movie_ids.includes(movieId ?? 0),
	)

	return (
		<Dialog open={movieId !== null} onOpenChange={(open) => !open && onClose()}>
			<DialogContent className="max-w-xl w-full max-h-[90vh] overflow-y-auto scrollbar-styled">
				{isLoading || !movie ? (
					<div className="h-64 flex items-center justify-center text-[var(--color-muted)] text-sm">
						Loading…
					</div>
				) : (
					<>
						<div className="flex gap-4">
							{movie.poster_url && (
								<img
									src={movie.poster_url}
									alt={movie.title}
									className="w-28 flex-shrink-0 rounded-lg object-cover"
								/>
							)}
							<div className="flex flex-col gap-2 flex-1 min-w-0">
								<DialogHeader>
									<DialogTitle className="leading-tight text-left">
										{movie.title}
										{movie.release_year && (
											<span className="text-[var(--color-muted)] font-sans text-sm ml-2">
												({movie.release_year})
											</span>
										)}
									</DialogTitle>
								</DialogHeader>

								{matchedCluster && (
									<div className="flex items-center gap-1.5">
										<span
											className="inline-block w-2 h-2 rounded-sm flex-shrink-0"
											style={{ backgroundColor: clusterColorFromUuid(matchedCluster.id, isDark) }}
										/>
										<span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs border border-[var(--color-border)] text-[var(--color-text)]">
											{matchedCluster.label ?? 'Unlabeled cluster'}
										</span>
									</div>
								)}

								<div className="flex flex-wrap gap-1">
									{movie.genres.map((g) => (
										<Badge key={g} variant="secondary">
											{g}
										</Badge>
									))}
								</div>

								<div className="text-xs flex gap-3 flex-wrap text-[var(--color-muted)]">
									{movie.runtime && <span>{movie.runtime} min</span>}
									{movie.vote_average != null && (
										<span>★ {movie.vote_average.toFixed(1)}</span>
									)}
								</div>

								<div className="text-xs space-y-1">
									{movie.director && (
										<div className="flex gap-2">
											<span className="w-16 shrink-0 uppercase tracking-wide text-[var(--color-muted)]">Director</span>
											<span className="text-[var(--color-text)]">{movie.director}</span>
										</div>
									)}
									{movie.top_cast.length > 0 && (
										<div className="flex gap-2">
											<span className="w-16 shrink-0 uppercase tracking-wide text-[var(--color-muted)]">Cast</span>
											<span className="text-[var(--color-text)]">{movie.top_cast.join(', ')}</span>
										</div>
									)}
								</div>
							</div>
						</div>

						{movie.overview && (
							<p className="text-sm text-[var(--color-text)] leading-relaxed mt-2">
								{movie.overview}
							</p>
						)}

						{movie.trailer_youtube_key && (
							<div className="mt-3 rounded-lg overflow-hidden aspect-video">
								<iframe
									src={`https://www.youtube.com/embed/${movie.trailer_youtube_key}`}
									title={`${movie.title} trailer`}
									className="w-full h-full"
									allowFullScreen
									loading="lazy"
								/>
							</div>
						)}
					</>
				)}
			</DialogContent>
		</Dialog>
	)
}