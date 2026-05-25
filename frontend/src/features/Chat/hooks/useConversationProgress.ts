import { useState, useEffect, useRef } from 'react'
import { openConversationEventStream } from '@/api/services/conversations'

/**
 * Opens an SSE stream for the given conversation and tracks the current pipeline step.
 * The stream is kept open for the lifetime of the conversation view; one per conversation.
 *
 * @param conversationId - Conversation UUID string, or undefined if not yet available.
 * @returns currentStep: the latest step key from the backend, or null between turns.
 */
export function useConversationProgress(conversationId: string | undefined): {
    currentStep: string | null
} {
    const [currentStep, setCurrentStep] = useState<string | null>(null)
    const sourceRef = useRef<EventSource | null>(null)

    useEffect(() => {
        if (!conversationId) return

        const source = openConversationEventStream(conversationId)
        sourceRef.current = source

        source.addEventListener('step', (e: MessageEvent) => {
            try {
                const data = JSON.parse(e.data) as { step?: string }
                if (data.step) setCurrentStep(data.step)
            } catch {
                // ignore malformed events
            }
        })

        source.addEventListener('turn_done', () => {
            setCurrentStep(null)
        })

        return () => {
            source.close()
            sourceRef.current = null
        }
    }, [conversationId])

    return { currentStep }
}
