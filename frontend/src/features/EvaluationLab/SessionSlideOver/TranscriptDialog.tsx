import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/dialog'
import { ClusterSnapshotTab } from '@/features/ClusterSnapshotTab/ClusterSnapshotTab'
import { ReadOnlyTranscript } from './ReadOnlyTranscript'

interface TranscriptDialogProps {
    conversationId: string
    open: boolean
    onOpenChange: (open: boolean) => void
}

/**
 * Centered dialog showing a session's read-only transcript on the left and
 * the cluster visualization (including the Evolution Map) on the right.
 */
export function TranscriptDialog({ conversationId, open, onOpenChange }: TranscriptDialogProps) {
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-[92vw] w-[92vw] h-[88vh] p-0 flex flex-col">
                <DialogHeader className="px-6 pt-4 pb-3 border-b border-[var(--color-border)] shrink-0">
                    <DialogTitle className="text-sm">Conversation replay</DialogTitle>
                </DialogHeader>

                <div className="flex flex-1 min-h-0">
                    <div className="basis-2/5 min-w-0 shrink-0 min-h-0 border-r border-[var(--color-border)] overflow-hidden flex flex-col">
                        <ReadOnlyTranscript conversationId={conversationId} />
                    </div>
                    <div className="basis-3/5 bg-[var(--color-surface)] overflow-hidden">
                        <ClusterSnapshotTab conversationId={conversationId} />
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}
