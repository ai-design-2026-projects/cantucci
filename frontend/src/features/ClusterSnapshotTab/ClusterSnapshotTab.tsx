import { useState } from 'react'
import { useSnapshotStore } from '@/store/useSnapshotStore'
import { useClusterSnapshot } from './hooks/useClusterSnapshot'
import { useExemplarMovies } from './hooks/useExemplarMovies'
import { useScatterData } from './hooks/useScatterData'
import { SnapshotPlot } from './components/SnapshotPlot'
import { ClusterList } from './components/ClusterList'
import { MoviePopup } from './components/MoviePopup'
import { EmptySnapshotState } from './components/EmptySnapshotState'

/**
 * Fixed right-panel showing the scatter plot of the active cluster snapshot
 * followed by a collapsible cluster list. Manages selected cluster and movie
 * popup state.
 *
 * @returns Right-panel content with scatter plot, cluster list, and movie popup.
 */
export function ClusterSnapshotTab() {
  const { activeSnapshotId, selectedClusterId, setSelectedClusterId } = useSnapshotStore()
  const [selectedMovieId, setSelectedMovieId] = useState<number | null>(null)

  const { data: snapshot } = useClusterSnapshot(activeSnapshotId)
  const { data: movieMap } = useExemplarMovies(snapshot)
  const scatterPoints = useScatterData(snapshot, movieMap)

  if (!snapshot) {
    return <EmptySnapshotState />
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Scatter plot occupies upper half */}
      <div className="flex-shrink-0 h-64">
        <SnapshotPlot
          points={scatterPoints}
          snapshot={snapshot}
          selectedClusterId={selectedClusterId}
          onPointClick={setSelectedMovieId}
        />
      </div>

      {/* Cluster list fills remaining space */}
      <div className="flex-1 overflow-hidden border-t border-[var(--color-border)]">
        <ClusterList
          snapshot={snapshot}
          movieMap={movieMap ?? new Map()}
          selectedClusterId={selectedClusterId}
          onSelectCluster={setSelectedClusterId}
          onMovieClick={setSelectedMovieId}
        />
      </div>

      <MoviePopup
        movieId={selectedMovieId}
        snapshot={snapshot}
        onClose={() => setSelectedMovieId(null)}
      />
    </div>
  )
}
