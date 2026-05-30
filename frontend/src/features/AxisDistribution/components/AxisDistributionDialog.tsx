import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/dialog'

import { useAxisDistribution } from '../hooks/useAxisDistribution'
import { DensityRidge } from './DensityRidge'

interface AxisDistributionDialogProps {
    open: boolean
    onClose: () => void
    conceptId: string
}

/**
 * Modal dialog that renders a horizontal beeswarm of movie scores along a
 * concept's linear axis.
 *
 * Data is fetched lazily — the query only fires when the dialog is open.
 *
 * @param open      - Whether the dialog is visible.
 * @param onClose   - Handler to dismiss the dialog.
 * @param conceptId - UUID of the concept whose axis to display.
 */
export function AxisDistributionDialog({ open, onClose, conceptId }: AxisDistributionDialogProps) {
    const { data, isLoading, isError } = useAxisDistribution(conceptId, open)

    return (
        <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
            <DialogContent className="max-w-4xl w-[92vw] max-h-[80vh] p-0 flex flex-col">
                <DialogHeader className="px-6 pt-5 pb-3 border-b border-[var(--color-border)]">
                    <DialogTitle>
                        How your films spread out
                    </DialogTitle>
                </DialogHeader>

                <div className="flex-1 overflow-y-auto scrollbar-styled px-4 py-5">
                    {isLoading && (
                        <div className="flex items-center justify-center h-40 text-sm text-[var(--color-muted)]">
                            Loading distribution…
                        </div>
                    )}
                    {isError && (
                        <div className="flex items-center justify-center h-40 text-sm text-[var(--color-muted)]">
                            Failed to load axis data.
                        </div>
                    )}
                    {data && <DensityRidge data={data} />}
                </div>
            </DialogContent>
        </Dialog>
    )
}
