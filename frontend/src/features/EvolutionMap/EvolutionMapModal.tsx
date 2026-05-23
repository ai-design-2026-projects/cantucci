import { useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'
import { useSnapshotStore } from '@/store/useSnapshotStore'
import { useSnapshotGraph } from './hooks/useSnapshotGraph'
import { ForceGraph } from './components/ForceGraph'
import { Button } from '@/components/button'

interface EvolutionMapModalProps {
  open: boolean
  onClose: () => void
  conversationId: string
}

/**
 * Full-bleed modal containing the force-directed cluster snapshot evolution graph.
 * Clicking a node updates the active snapshot and closes the modal.
 *
 * @param open           - Controls modal visibility.
 * @param onClose        - Called when the modal should close.
 * @param conversationId - Conversation UUID used to load the snapshot DAG.
 * @returns Framer Motion modal overlay with ForceGraph.
 */
export function EvolutionMapModal({ open, onClose, conversationId }: EvolutionMapModalProps) {
  const [, setSearchParams] = useSearchParams()
  const { activeSnapshotId, setActiveSnapshotId } = useSnapshotStore()
  const { data: graph } = useSnapshotGraph(conversationId)
  function handleNodeClick(nodeId: string) {
    setActiveSnapshotId(nodeId)
    setSearchParams({ snapshot: nodeId })
    onClose()
  }

  const nodes = graph?.cluster_snapshots ?? []

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            className="relative w-full max-w-3xl h-[70vh] bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] overflow-hidden shadow-2xl"
            initial={{ scale: 0.92, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.92, opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)]">
              <h2 className="text-lg font-display text-[var(--color-text)]">Snapshot Evolution</h2>
              <Button variant="ghost" size="icon" onClick={onClose}>
                <X className="h-4 w-4" />
              </Button>
            </div>

            {nodes.length === 0 ? (
              <div className="flex items-center justify-center h-full text-sm text-[var(--color-muted)]">
                No snapshots yet
              </div>
            ) : (
              <ForceGraph
                nodes={nodes}
                activeSnapshotId={activeSnapshotId}
                onNodeClick={handleNodeClick}
                width={window.innerWidth > 900 ? 760 : window.innerWidth - 80}
                height={500}
              />
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
