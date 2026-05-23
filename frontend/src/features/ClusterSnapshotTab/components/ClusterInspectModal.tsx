import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/dialog'
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/tooltip'
import { clusterColorFromUuid } from '@/styles/theme'
import { useThemeStore } from '@/store/useThemeStore'
import type { ClusterDto, ClusterSnapshotDto, MovieDto } from '@/lib/types'

interface ClusterInspectModalProps {
  open: boolean
  onClose: () => void
  snapshot: ClusterSnapshotDto
  movieMap: Map<number, MovieDto>
  onMovieClick: (movieId: number) => void
}

interface ClusterInspectCardProps {
  cluster: ClusterDto
  color: string
  movieMap: Map<number, MovieDto>
  onMovieClick: (movieId: number) => void
}

function ClusterInspectCard({ cluster, color, movieMap, onMovieClick }: ClusterInspectCardProps) {
  const exemplars = cluster.exemplar_movie_ids
    .map((id) => movieMap.get(id))
    .filter((m): m is MovieDto => m !== undefined)

  return (
    <div className="relative rounded-lg border border-[var(--color-border)] bg-[var(--color-elevated)]">
      <div
        className="absolute left-0 top-0 bottom-0 w-1 rounded-l-lg"
        style={{ backgroundColor: color }}
      />
      <div className="pl-5 pr-4 pt-4 pb-3 min-w-0">
        <div className="flex items-baseline justify-between gap-2">
          <h4 className="font-display text-base text-[var(--color-text)] tracking-tight leading-tight">
            {cluster.label ?? 'Unlabeled'}
          </h4>
          <span className="text-xs text-[var(--color-muted)] flex-shrink-0">{cluster.size} films</span>
        </div>
        {cluster.summary && (
          <p className="mt-0.5 text-xs text-[var(--color-muted)] leading-relaxed">{cluster.summary}</p>
        )}
        {exemplars.length > 0 && (
          <div className="mt-3 -mx-1 overflow-x-auto pb-1 px-1">
            <div className="flex flex-nowrap gap-1.5">
              {exemplars.map((movie) => (
                <Tooltip key={movie.id}>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={() => onMovieClick(movie.id)}
                      className="shrink-0 w-12 h-[72px] rounded overflow-hidden bg-[var(--color-bg)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]"
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

/**
 * Modal popup showing all clusters in the active snapshot as rich cards.
 * Each card has a color stripe, display-font title, description, and a
 * horizontal film thumbnail strip with hover tooltips.
 *
 * @param open         - Whether the dialog is visible.
 * @param onClose      - Handler to dismiss the dialog.
 * @param snapshot     - Active cluster snapshot.
 * @param movieMap     - Map from movie ID to MovieDto (pre-fetched by parent).
 * @param onMovieClick - Opens the movie detail popup for a given movie ID.
 * @returns Centered dialog with scrollable cluster card list.
 */
export function ClusterInspectModal({
  open,
  onClose,
  snapshot,
  movieMap,
  onMovieClick,
}: ClusterInspectModalProps) {
  const isDark = useThemeStore((s) => s.theme === 'dark')

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-3xl w-[90vw] max-h-[85vh] p-0 flex flex-col">
        <DialogHeader className="px-6 pt-5 pb-3 border-b border-[var(--color-border)]">
          <DialogTitle>Clusters</DialogTitle>
          <p className="text-xs text-[var(--color-muted)] mt-0.5">
            {snapshot.clusters.length} cluster{snapshot.clusters.length !== 1 ? 's' : ''}
          </p>
        </DialogHeader>
        <TooltipProvider delayDuration={300}>
          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
            {snapshot.clusters.map((cluster) => (
              <ClusterInspectCard
                key={cluster.id}
                cluster={cluster}
                color={clusterColorFromUuid(cluster.id, isDark)}
                movieMap={movieMap}
                onMovieClick={onMovieClick}
              />
            ))}
          </div>
        </TooltipProvider>
      </DialogContent>
    </Dialog>
  )
}
