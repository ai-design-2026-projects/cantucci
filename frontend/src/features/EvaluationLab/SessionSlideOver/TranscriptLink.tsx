import { useState } from 'react'
import { MessagesSquare } from 'lucide-react'
import { Button } from '@/components/button'
import { TranscriptDialog } from './TranscriptDialog'

interface TranscriptLinkProps {
    conversationId: string
}

/**
 * Button that opens the conversation transcript and cluster visualization
 * in a centered dialog, without leaving the evaluation dashboard.
 */
export function TranscriptLink({ conversationId }: TranscriptLinkProps) {
    const [open, setOpen] = useState(false)

    return (
        <>
            <Button
                variant="outline"
                size="sm"
                className="gap-1.5 text-xs"
                onClick={() => setOpen(true)}
            >
                <MessagesSquare className="h-3.5 w-3.5" />
                View transcript
            </Button>
            <TranscriptDialog
                conversationId={conversationId}
                open={open}
                onOpenChange={setOpen}
            />
        </>
    )
}
