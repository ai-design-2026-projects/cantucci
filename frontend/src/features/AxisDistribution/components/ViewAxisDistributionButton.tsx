import { useState } from 'react'
import { BarChart2 } from 'lucide-react'

import { Button } from '@/components/button'
import { AxisDistributionDialog } from './AxisDistributionDialog'

interface ViewAxisDistributionButtonProps {
    conceptId: string
}

/**
 * Inline button that opens the axis distribution beeswarm dialog for a given concept.
 *
 * Intended to be rendered inside a chat message bubble when the assistant has
 * proposed a concept-axis clustering and is awaiting a cluster-count confirmation.
 *
 * @param conceptId - UUID of the persisted concept whose normalized scores to display.
 */
export function ViewAxisDistributionButton({ conceptId }: ViewAxisDistributionButtonProps) {
    const [open, setOpen] = useState(false)

    return (
        <>
            <Button
                variant="outline"
                size="sm"
                onClick={() => setOpen(true)}
                className="mt-2 gap-1.5 text-xs"
            >
                <BarChart2 className="h-3.5 w-3.5" />
                View axis distribution
            </Button>

            {open && (
                <AxisDistributionDialog
                    open={open}
                    onClose={() => setOpen(false)}
                    conceptId={conceptId}
                />
            )}
        </>
    )
}
