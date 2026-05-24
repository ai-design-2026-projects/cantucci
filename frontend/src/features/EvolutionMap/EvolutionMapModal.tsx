import { useRef, useState, useMemo, useEffect } from 'react'
import { useQueries, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Crosshair, Trash2, History } from 'lucide-react'
import { toast } from 'sonner'
import { useSnapshotStore } from '@/store/useSnapshotStore'
import { useSnapshotGraph } from './hooks/useSnapshotGraph'
import { useDeleteSnapshot } from './hooks/useDeleteSnapshot'
import { useSetActiveSnapshot } from './hooks/useSetActiveSnapshot'
import { SnapshotGraph } from './components/SnapshotGraph'
import { DeleteSnapshotDialog } from './components/DeleteSnapshotDialog'
import { ResetHistoryDialog } from './components/ResetHistoryDialog'
import { radialLayout } from './lib/radialLayout'
import { resetHistory } from './lib/resetHistory'
import { getSnapshotFetcher } from '@/api/services/snapshots'
import { Button } from '@/components/button'
import type { SnapshotGraphHandle } from './components/SnapshotGraph'
import type { LayoutNode } from './lib/radialLayout'

interface EvolutionMapModalProps {
	open: boolean
	onClose: () => void
	conversationId: string
}

/**
 * Modal showing the cluster snapshot evolution as a radial SVG graph.
 * Root snapshot sits at center; descendants fan out in concentric rings.
 * Clicking a node sets it as the conversation's active snapshot (persisted
 * to the backend via PATCH /conversations/{id}). Hovering a non-root node
 * exposes a delete affordance; deletion requires no children.
 *
 * @param open           - Controls modal visibility.
 * @param onClose        - Called when the modal should close.
 * @param conversationId - Conversation UUID used to load and mutate snapshots.
 * @returns Framer Motion modal overlay with radial snapshot graph.
 */
export function EvolutionMapModal({ open, onClose, conversationId }: EvolutionMapModalProps) {
	const { activeSnapshotId } = useSnapshotStore()
	const { data: graph } = useSnapshotGraph(conversationId)
	const { mutate: setActiveSnapshot, isPending: isSettingActive } = useSetActiveSnapshot(conversationId)
	const { mutate: deleteSnapshot, isPending: isDeleting } = useDeleteSnapshot(conversationId)

	const queryClient = useQueryClient()
	const graphRef = useRef<SnapshotGraphHandle>(null)
	const bodyRef = useRef<HTMLDivElement>(null)
	const [bodySize, setBodySize] = useState({ w: 0, h: 0 })
	const [deleteTarget, setDeleteTarget] = useState<LayoutNode | null>(null)
	const [resetDialogOpen, setResetDialogOpen] = useState(false)
	const [isResetting, setIsResetting] = useState(false)

	const nodes = graph?.cluster_snapshots ?? []
	const layout = useMemo(() => radialLayout(nodes), [nodes])

	const snapshotQueries = useQueries({
		queries: nodes.map((node) => ({
			queryKey: ['snapshot', node.id],
			queryFn: () => getSnapshotFetcher(node.id),
			enabled: open && nodes.length > 0,
			staleTime: 60_000,
		})),
	})

	const clusterCounts = useMemo(() => {
		const counts = new Map<string, number>()
		nodes.forEach((node, index) => {
			counts.set(node.id, snapshotQueries[index]?.data?.clusters.length ?? 0)
		})
		return counts
	}, [nodes, snapshotQueries])

	const childCounts = useMemo(() => {
		const counts = new Map<string, number>()
		for (const n of nodes) {
			if (n.parent_id) {
				counts.set(n.parent_id, (counts.get(n.parent_id) ?? 0) + 1)
			}
		}
		return counts
	}, [nodes])

	const activeLayoutNode: LayoutNode | null = layout.find((n) => n.id === activeSnapshotId) ?? null

	useEffect(() => {
		if (!bodyRef.current) return
		const obs = new ResizeObserver((entries) => {
			const { width, height } = entries[0].contentRect
			setBodySize({ w: Math.floor(width), h: Math.floor(height) })
		})
		obs.observe(bodyRef.current)
		return () => obs.disconnect()
	}, [open])

	function handleNodeClick(nodeId: string) {
		if (nodeId === activeSnapshotId || isSettingActive) return
		setActiveSnapshot(nodeId)
	}

	function handleDeleteConfirm() {
		if (!deleteTarget) return
		const parentId = deleteTarget.parent_id
		deleteSnapshot(deleteTarget.id, {
			onSuccess: () => {
				setDeleteTarget(null)
				if (parentId) setActiveSnapshot(parentId)
			},
		})
	}

	async function handleResetConfirm() {
		setIsResetting(true)
		try {
			await resetHistory(layout)
			const baseNode = layout.find((n) => n.operation === 'base')
			if (baseNode) setActiveSnapshot(baseNode.id)
			queryClient.invalidateQueries({ queryKey: ['snapshot-graph', conversationId] })
			toast.success('Snapshot history reset')
		} catch (err) {
			toast.error((err as Error).message || 'Could not reset history')
		} finally {
			setIsResetting(false)
			setResetDialogOpen(false)
		}
	}

	const nonBaseCount = layout.filter((n) => n.operation !== 'base').length

	return (
		<>
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
							className="relative w-full max-w-5xl h-[80vh] bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] overflow-hidden shadow-2xl flex flex-col"
							initial={{ scale: 0.92, opacity: 0 }}
							animate={{ scale: 1, opacity: 1 }}
							exit={{ scale: 0.92, opacity: 0 }}
							transition={{ duration: 0.2 }}
							onClick={(e) => e.stopPropagation()}
						>
							{/* Header */}
							<div className="flex items-center justify-between px-6 py-3 border-b border-[var(--color-border)] flex-shrink-0">
								<h2 className="text-lg font-display text-[var(--color-text)]">Snapshot Evolution</h2>
								<div className="flex items-center gap-1">
									{activeLayoutNode && activeLayoutNode.operation !== 'base' && (
										<Button
											variant="ghost"
											size="sm"
											onClick={() => setDeleteTarget(activeLayoutNode)}
											disabled={isDeleting}
											className="gap-1.5 text-[var(--color-muted)] hover:text-red-500"
										>
											<Trash2 className="h-3.5 w-3.5" />
											<span className="text-xs hidden sm:inline">Remove</span>
										</Button>
									)}
									{nonBaseCount > 0 && (
										<Button
											variant="ghost"
											size="sm"
											onClick={() => setResetDialogOpen(true)}
											disabled={isResetting}
											className="gap-1.5 text-[var(--color-muted)] hover:text-red-500"
										>
											<History className="h-3.5 w-3.5" />
											<span className="text-xs hidden sm:inline">Reset</span>
										</Button>
									)}
									<Button
										variant="ghost"
										size="sm"
										onClick={() => graphRef.current?.reset()}
										className="gap-1.5"
									>
										<Crosshair className="h-3.5 w-3.5" />
										<span className="text-xs hidden sm:inline">Recenter</span>
									</Button>
									<Button variant="ghost" size="icon" onClick={onClose}>
										<X className="h-4 w-4" />
									</Button>
								</div>
							</div>

							{/* Graph body */}
							<div ref={bodyRef} className="flex-1 min-h-0">
								{nodes.length === 0 ? (
									<div className="flex items-center justify-center h-full text-sm text-[var(--color-muted)]">
										No snapshots yet
									</div>
								) : bodySize.w > 0 && bodySize.h > 0 ? (
									<SnapshotGraph
										ref={graphRef}
										layout={layout}
										activeSnapshotId={activeSnapshotId}
										clusterCounts={clusterCounts}
										onNodeClick={handleNodeClick}
										width={bodySize.w}
										height={bodySize.h}
									/>
								) : null}
							</div>
						</motion.div>
					</motion.div>
				)}
			</AnimatePresence>

			<DeleteSnapshotDialog
				node={deleteTarget}
				childCount={deleteTarget ? (childCounts.get(deleteTarget.id) ?? 0) : 0}
				isPending={isDeleting}
				onConfirm={handleDeleteConfirm}
				onClose={() => setDeleteTarget(null)}
			/>

			<ResetHistoryDialog
				open={resetDialogOpen}
				snapshotCount={nonBaseCount}
				isPending={isResetting}
				onConfirm={handleResetConfirm}
				onClose={() => setResetDialogOpen(false)}
			/>
		</>
	)
}
