import { ChevronDown, ChevronRight } from 'lucide-react'
import { clusterColorFromUuid } from '@/styles/theme'
import { useThemeStore } from '@/store/useThemeStore'
import { ClusterDetail } from './ClusterDetail'
import type { ClusterDto, ClusterSnapshotDto, MovieDto } from '@/lib/types'

interface ClusterListProps {
  snapshot: ClusterSnapshotDto
  movieMap: Map<number, MovieDto>
  selectedClusterId: string | null
  onSelectCluster: (id: string | null) => void
  onMovieClick: (movieId: number) => void
}

interface ClusterRowProps {
  cluster: ClusterDto
  color: string
  isSelected: boolean
  movieMap: Map<number, MovieDto>
  onSelect: () => void
  onMovieClick: (movieId: number) => void
}

/**
 * Single cluster row that expands to show exemplar cards on click.
 *
 * @param cluster     - Cluster to display.
 * @param color       - Deterministic HSL color for this cluster.
 * @param isSelected  - Whether this cluster is currently expanded/selected.
 * @param movieMap    - Movie lookup map.
 * @param onSelect    - Toggles this cluster's selected state.
 * @param onMovieClick - Opens movie popup.
 * @returns Clickable cluster row with optional expanded detail.
 */
function ClusterRow({ cluster, color, isSelected, movieMap, onSelect, onMovieClick }: ClusterRowProps) {
  return (
    <div className="border-b border-[var(--color-border)] last:border-0">
      <button
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-[var(--color-elevated)] transition-colors"
        onClick={onSelect}
      >
        <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: color }} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-[var(--color-text)] truncate">
            {cluster.label ?? 'Unlabeled'}
          </p>
          {cluster.summary && (
            <p className="text-xs text-[var(--color-muted)] truncate">{cluster.summary}</p>
          )}
        </div>
        <span className="text-xs text-[var(--color-muted)] flex-shrink-0">{cluster.size}</span>
        {isSelected ? (
          <ChevronDown className="h-3 w-3 text-[var(--color-muted)] flex-shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 text-[var(--color-muted)] flex-shrink-0" />
        )}
      </button>
      {isSelected && (
        <ClusterDetail cluster={cluster} movieMap={movieMap} onMovieClick={onMovieClick} />
      )}
    </div>
  )
}

/**
 * Collapsible list of all clusters in the active snapshot.
 * Selecting a cluster expands its exemplar detail and dims others on the scatter plot.
 *
 * @param snapshot         - Active cluster snapshot.
 * @param movieMap         - Map from movie ID to MovieDto.
 * @param selectedClusterId - Currently selected cluster ID (or null for none).
 * @param onSelectCluster  - Updates the selected cluster in the parent.
 * @param onMovieClick     - Opens the movie detail popup.
 * @returns Scrollable cluster list.
 */
export function ClusterList({
  snapshot,
  movieMap,
  selectedClusterId,
  onSelectCluster,
  onMovieClick,
}: ClusterListProps) {
  const isDark = useThemeStore((s) => s.theme === 'dark')

  return (
    <div className="flex flex-col overflow-y-auto">
      {snapshot.clusters.map((cluster) => {
        const color = clusterColorFromUuid(cluster.id, isDark)
        return (
          <ClusterRow
            key={cluster.id}
            cluster={cluster}
            color={color}
            isSelected={selectedClusterId === cluster.id}
            movieMap={movieMap}
            onSelect={() => onSelectCluster(selectedClusterId === cluster.id ? null : cluster.id)}
            onMovieClick={onMovieClick}
          />
        )
      })}
    </div>
  )
}
