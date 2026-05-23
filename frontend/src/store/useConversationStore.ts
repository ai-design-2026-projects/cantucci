import { create } from 'zustand'
import { ANON_CONVERSATION_KEY } from '@/lib/constants'

interface ConversationState {
	activeConversationId: string | null
	setActiveConversationId: (id: string | null) => void
	loadAnonConversationId: () => string | null
	saveAnonConversationId: (id: string) => void
	clearAnonConversationId: () => void
}

/**
 * Manages the active conversation ID and anonymous session persistence.
 * Anonymous users' conversation ID is stored in localStorage to survive reloads.
 */
export const useConversationStore = create<ConversationState>((set) => ({
	activeConversationId: null,

	setActiveConversationId: (id) => set({ activeConversationId: id }),

	loadAnonConversationId: () => {
		return localStorage.getItem(ANON_CONVERSATION_KEY)
	},

	saveAnonConversationId: (id) => {
		localStorage.setItem(ANON_CONVERSATION_KEY, id)
		set({ activeConversationId: id })
	},

	clearAnonConversationId: () => {
		localStorage.removeItem(ANON_CONVERSATION_KEY)
	},
}))
