import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/dialog'
import { Button } from '@/components/button'
import type { LayoutNode } from '../lib/radialLayout'

/**
 * Confirmation dialog for deleting a cluster snapshot.
 * Disabled when the snapshot still has children.
 *
 * @param node       - Snapshot node to delete, or null when closed.
 * @param childCount - Number of children this snapshot has.
 * @param isPending  - Whether the delete mutation is in-flight.
 * @param onConfirm  - Called when the user confirms deletion.
 * @param onClose    - Called when the dialog is dismissed.
 */
export function DeleteSnapshotDialog({
	node,
	childCount,
	isPending,
	onConfirm,
	onClose,
}: {
	node: LayoutNode | null
	childCount: number
	isPending: boolean
	onConfirm: () => void
	onClose: () => void
}) {
	if (!node) return null

	const label =
		node.operation === 'base'
			? 'Base snapshot'
			: `${node.operation.replace('_', ' ')} #${node.sopIndex}`

	const createdAt = new Date(node.created_at).toLocaleString(undefined, {
		dateStyle: 'medium',
		timeStyle: 'short',
	})

	const hasChildren = childCount > 0

	return (
		<Dialog open={!!node} onOpenChange={(open) => !open && onClose()}>
			<DialogContent className="max-w-sm">
				<DialogHeader>
					<DialogTitle>Delete snapshot?</DialogTitle>
				</DialogHeader>
				<div className="space-y-3 text-sm text-[var(--color-text)]">
					<p>
						<span className="font-medium capitalize">{label}</span>
						<span className="text-[var(--color-muted)]"> — created {createdAt}</span>
					</p>
					{hasChildren ? (
						<p className="text-[var(--color-muted)]">
							This snapshot has {childCount} child snapshot{childCount !== 1 ? 's' : ''}.
							Delete those first before deleting this one.
						</p>
					) : (
						<p className="text-[var(--color-muted)]">
							This will permanently remove the snapshot and all its cluster memberships.
							Conversations pointing here will be moved to its parent.
						</p>
					)}
				</div>
				<div className="flex justify-end gap-2 mt-2">
					<Button variant="ghost" size="sm" onClick={onClose} disabled={isPending}>
						Cancel
					</Button>
					<Button
						variant="destructive"
						size="sm"
						onClick={onConfirm}
						disabled={hasChildren || isPending}
					>
						{isPending ? 'Deleting…' : 'Delete'}
					</Button>
				</div>
			</DialogContent>
		</Dialog>
	)
}
