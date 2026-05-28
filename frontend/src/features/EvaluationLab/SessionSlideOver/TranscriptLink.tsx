import { ExternalLink } from 'lucide-react'
import { Button } from '@/components/button'

interface TranscriptLinkProps {
    conversationId: string
}

/**
 * Link that opens the conversation transcript in the main app in a new tab.
 */
export function TranscriptLink({ conversationId }: TranscriptLinkProps) {
    return (
        <Button
            variant="outline"
            size="sm"
            className="gap-1.5 text-xs"
            onClick={() => window.open(`/conversation/${conversationId}`, '_blank', 'noreferrer')}
        >
            <ExternalLink className="h-3.5 w-3.5" />
            View transcript
        </Button>
    )
}
