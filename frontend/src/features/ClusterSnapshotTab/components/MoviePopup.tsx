import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/dialog'
import { Badge } from '@/components/badge'
import { useMovieDetails } from '../hooks/useMovieDetails'
import type { ClusterSnapshotDto } from '@/api/snapshots'

interface MoviePopupProps {
  movieId: number | null
  snapshot: ClusterSnapshotDto | undefined
  onClose: () => void
}

/**
 * Movie detail dialog showing poster, overview, metadata, and trailer.
 * Fetches full movie details when a movieId is selected.
 *
 * @param movieId  - TMDB ID of the movie to display, or null when closed.
 * @param snapshot - Active snapshot used to identify which cluster this movie belongs to.
 * @param onClose  - Called when the dialog is dismissed.
 * @returns Radix Dialog with full movie metadata.
 */
export function MoviePopup({ movieId, snapshot, onClose }: MoviePopupProps) {
  const { data: movie, isLoading } = useMovieDetails(movieId)

  const clusterLabel = snapshot?.clusters.find((c) =>
    c.exemplar_movie_ids.includes(movieId ?? 0),
  )?.label

  return (
    <Dialog open={movieId !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-xl w-full max-h-[90vh] overflow-y-auto">
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

                <div className="flex flex-wrap gap-1 mt-1">
                  {movie.genres.map((g) => (
                    <Badge key={g} variant="secondary">{g}</Badge>
                  ))}
                </div>

                <div className="text-xs text-[var(--color-muted)] flex gap-3 flex-wrap">
                  {movie.director && <span>Dir. {movie.director}</span>}
                  {movie.runtime && <span>{movie.runtime} min</span>}
                  {movie.vote_average != null && (
                    <span>★ {movie.vote_average.toFixed(1)}</span>
                  )}
                </div>

                {movie.top_cast.length > 0 && (
                  <p className="text-xs text-[var(--color-muted)]">
                    {movie.top_cast.join(' · ')}
                  </p>
                )}
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

            {clusterLabel && (
              <p className="text-xs text-[var(--color-muted)] border-t border-[var(--color-border)] pt-3 mt-1">
                In cluster: <span className="font-medium text-[var(--color-text)]">{clusterLabel}</span>
              </p>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
