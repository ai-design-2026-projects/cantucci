import type { MovieDto } from '@/api/dto/movies'

/**
 * Compact movie card showing poster thumbnail, title, and year.
 * Used in the cluster detail expanded view.
 *
 * @param movie   - MovieDto to display.
 * @param onClick - Called with the movie ID when the card is clicked.
 * @returns Clickable movie card.
 */
export function ExemplarCard({
	movie,
	onClick,
}: {
	movie: MovieDto
	onClick: (movieId: number) => void
}) {
	return (
		<button
			className="flex flex-col gap-1 cursor-pointer text-left hover:opacity-80 transition-opacity"
			onClick={() => onClick(movie.id)}
		>
			{movie.poster_url ? (
				<img
					src={movie.poster_url}
					alt={movie.title}
					className="w-full rounded-lg object-cover aspect-[2/3]"
					loading="lazy"
				/>
			) : (
				<div className="w-full rounded-lg bg-[var(--color-elevated)] aspect-[2/3] flex items-center justify-center text-xs text-[var(--color-muted)]">
					No poster
				</div>
			)}
			<p className="text-xs font-medium text-[var(--color-text)] leading-tight line-clamp-2">
				{movie.title}
			</p>
			{movie.release_year && (
				<p className="text-xs text-[var(--color-muted)]">{movie.release_year}</p>
			)}
		</button>
	)
}
