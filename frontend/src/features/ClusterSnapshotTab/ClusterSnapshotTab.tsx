import { useState } from 'react'
import { useSnapshotStore } from '@/store/useSnapshotStore'
import { useClusterSnapshot } from './hooks/useClusterSnapshot'
import { useExemplarMovies } from './hooks/useExemplarMovies'
import { useScatterData } from './hooks/useScatterData'
import { SnapshotPlot } from './components/SnapshotPlot'
import { ClusterList } from './components/ClusterList'
import { MoviePopup } from './components/MoviePopup'
import { EmptySnapshotState } from './components/EmptySnapshotState'
import { EvolutionMapButton } from '@/features/Header/components/EvolutionMapButton'
import { EvolutionMapModal } from '@/features/EvolutionMap/EvolutionMapModal'
import { InspectButton } from './components/InspectButton'
import { ClusterInspectModal } from './components/ClusterInspectModal'

interface ClusterSnapshotTabProps {
  conversationId: string
}

/**
 * Fixed right-panel showing the scatter plot of the active cluster snapshot
 * followed by a collapsible cluster list. Owns the Evolution Map modal state.
 *
 * @param conversationId - Active conversation UUID passed to the evolution modal.
 * @returns Right-panel content with header, scatter plot, cluster list, and movie popup.
 */
export function ClusterSnapshotTab({ conversationId }: ClusterSnapshotTabProps) {
  const { activeSnapshotId, selectedClusterId, setSelectedClusterId } = useSnapshotStore()
  const [selectedMovieId, setSelectedMovieId] = useState<number | null>(null)
  const [evolutionOpen, setEvolutionOpen] = useState(false)
  const [inspectOpen, setInspectOpen] = useState(false)

  const { data: snapshot } = useClusterSnapshot(activeSnapshotId)
  const { data: movieMap } = useExemplarMovies(snapshot)
  const scatterPoints = useScatterData(snapshot, movieMap)

  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--color-border)] flex-shrink-0">
        <span className="text-sm font-medium text-[var(--color-text)]">Cluster Snapshot</span>
        <div className="flex items-center gap-1">
          <InspectButton onClick={() => setInspectOpen(true)} disabled={!snapshot} />
          <EvolutionMapButton onClick={() => setEvolutionOpen(true)} />
        </div>
      </div>

      {!snapshot ? (
        <EmptySnapshotState />
      ) : (
        <>
          <div className="flex-shrink-0 h-full w-full">
            <SnapshotPlot
              points={scatterPoints}
              snapshot={snapshot}
              selectedClusterId={selectedClusterId}
              onPointClick={setSelectedMovieId}
            />
          </div>

          <MoviePopup
            movieId={selectedMovieId}
            snapshot={snapshot}
            onClose={() => setSelectedMovieId(null)}
          />
        </>
      )}

      <EvolutionMapModal
        open={evolutionOpen}
        onClose={() => setEvolutionOpen(false)}
        conversationId={conversationId}
      />
      {snapshot && (
        <ClusterInspectModal
          open={inspectOpen}
          onClose={() => setInspectOpen(false)}
          snapshot={snapshot}
          movieMap={movieMap ?? new Map()}
          onMovieClick={(id) => setSelectedMovieId(id)}
        />
      )}
    </div>
  )
}
