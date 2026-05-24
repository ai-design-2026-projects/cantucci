import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/tooltip'
import type { ClusterDto } from '@/api/dto/snapshots'
import type { MovieDto } from '@/api/dto/movies'

/**
 * Rich card used inside the cluster inspect dialog to show one cluster and its exemplar movies.
 *
 * @param cluster      - Cluster metadata shown in the card body.
 * @param color        - Accent stripe color for the cluster.
 * @param movieMap     - Map from movie ID to hydrated movie metadata.
 * @param onMovieClick - Opens the mo  8  |  import { ClusterInspectModal } from "@/features/ClustersInspect/ClusterInspectModal";vie popup for a clicked exemplar.
 * @returns Clickable cluster summary card.
 */
export function ClusterInspectCard({
	cluster,
	color,
	movieMap,
	onMovieClick,
}: {
	cluster: ClusterDto
	color: string
	movieMap: Map<number, MovieDto>
	onMovieClick: (movieId: number) => void
}) {
	const exemplars = cluster.exemplar_movie_ids
		.map((id) => movieMap.get(id))
		.filter((m): m is MovieDto => m !== undefined)

	return (
		<div className="relative rounded-lg border border-[var(--color-border)] bg-[var(--color-elevated)]">
			<div
				className="absolute left-0 top-0 bottom-0 w-1 rounded-l-lg"
				style={{ backgroundColor: color }}
			/>
			<div className="pl-6 pr-6 pt-5 pb-4 min-w-0 font-sans">
				<div className="flex items-baseline justify-between gap-3">
					<h4 className="text-base text-[var(--color-text)] tracking-tight leading-tight font-medium">
						{cluster.label ?? 'Unlabeled'}
					</h4>
					<span className="text-xs text-[var(--color-muted)] flex-shrink-0">{cluster.size} films</span>
				</div>
				{cluster.summary && (
					<p className="mt-1 text-xs text-[var(--color-muted)] leading-relaxed">{cluster.summary}</p>
				)}
				{exemplars.length > 0 && (
					<div className="mt-4 -mx-2 overflow-x-auto pb-2 px-2">
						<div className="flex flex-nowrap gap-2">
							{exemplars.map((movie) => (
								<Tooltip key={movie.id}>
									<TooltipTrigger asChild>
										<button
											type="button"
											onClick={() => onMovieClick(movie.id)}
											className="shrink-0 w-24 h-[144px] rounded overflow-hidden bg-[var(--color-bg)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]"
										>
											{movie.poster_url ? (
												<img
													src={movie.poster_url}
													alt={movie.title}
													className="w-full h-full object-cover hover:scale-110 transition-transform duration-200"
													loading="lazy"
												/>
											) : (
												<div className="w-full h-full flex items-center justify-center text-[var(--color-muted)] text-[0.5rem] p-1 text-center leading-tight">
													{movie.title}
												</div>
											)}
										</button>
									</TooltipTrigger>
									<TooltipContent side="bottom">
										<p className="font-medium">{movie.title}</p>
										{movie.release_year && (
											<p className="text-[var(--color-muted)] text-xs">{movie.release_year}</p>
										)}
									</TooltipContent>
								</Tooltip>
							))}
						</div>
					</div>
				)}
			</div>
		</div>
	)
}