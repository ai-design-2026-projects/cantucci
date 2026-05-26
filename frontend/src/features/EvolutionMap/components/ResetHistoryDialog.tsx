import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/dialog'
import { Button } from '@/components/button'

/**
 * Confirmation dialog for wiping all non-base snapshots.
 *
 * @param open           - Whether the dialog is visible.
 * @param snapshotCount  - Number of non-base snapshots that will be deleted.
 * @param isPending      - Whether the delete operation is in-flight.
 * @param onConfirm      - Called when the user confirms.
 * @param onClose        - Called when the dialog is dismissed.
 */
export function ResetHistoryDialog({
    open,
    snapshotCount,
    isPending,
    onConfirm,
    onClose,
}: {
    open: boolean
    snapshotCount: number
    isPending: boolean
    onConfirm: () => void
    onClose: () => void
}) {
    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-sm">
                <DialogHeader>
                    <DialogTitle>Reset snapshot history?</DialogTitle>
                </DialogHeader>
                <div className="space-y-3 text-sm text-[var(--color-text)]">
                    <p className="text-[var(--color-muted)]">
                        {snapshotCount > 0
                            ? `This will permanently delete ${snapshotCount} snapshot${snapshotCount !== 1 ? 's' : ''} and return to the unclustered state. This cannot be undone.`
                            : 'This will return to the unclustered state.'}
                    </p>
                </div>
                <div className="flex justify-end gap-2 mt-2">
                    <Button variant="ghost" size="sm" onClick={onClose} disabled={isPending}>
                        Cancel
                    </Button>
                    <Button variant="destructive" size="sm" onClick={onConfirm} disabled={isPending}>
                        {isPending ? 'Deleting…' : 'Reset'}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    )
}
