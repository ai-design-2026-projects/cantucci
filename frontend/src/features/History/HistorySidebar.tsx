import { Plus, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { Button } from '@/components/button'
import { ConversationListItem } from './components/ConversationListItem'
import { AuthGatePrompt } from './components/AuthGatePrompt'
import { useHistorySidebarData } from './hooks/useHistorySidebarData'
import { useHistorySidebarHandlers } from './hooks/useHistorySidebarHandlers'

/**
 * Collapsible left sidebar showing the authenticated user's conversation history.
 * Default state is collapsed. Toggle persists to localStorage.
 *
 * @returns Animated left-column sidebar with conversation list or auth prompt.
 */
export function HistorySidebar() {
	const { open, user, activeId, conversations, isLoading, setOpen, setActiveConversationId } = useHistorySidebarData()
	const { toggleSidebar, selectConversation, createConversation, deleteConversation, creating } = useHistorySidebarHandlers({
		open,
		setOpen,
		setActiveConversationId,
	})

	return (
		<div
			className={`flex-shrink-0 flex flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] transition-all duration-200 overflow-hidden ${open ? 'w-72' : 'w-14'}`}
		>
			<div className={`flex items-center border-b border-[var(--color-border)] h-12 flex-shrink-0 ${open ? 'justify-between px-3' : 'justify-center'}`}>
				{open && (
					<span className="text-sm font-medium text-[var(--color-text)]">History</span>
				)}
				<Button variant="ghost" size="icon" onClick={toggleSidebar} className="h-8 w-8">
					{open ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
				</Button>
			</div>

			{open ? (
				<>
					{!user ? (
						<AuthGatePrompt />
					) : (
						<>
							<div className="flex-1 overflow-y-auto">
								{isLoading && (
									<p className="text-xs text-[var(--color-muted)] px-4 py-3">Loading…</p>
								)}
								{!isLoading && conversations.length === 0 && (
									<p className="text-xs text-[var(--color-muted)] px-4 py-3">No conversations yet</p>
								)}
								{conversations.map((conv) => (
									<ConversationListItem
										key={conv.id}
										conversation={conv}
										isActive={conv.id === activeId}
										onSelect={() => selectConversation(conv.id)}
										onDelete={() => deleteConversation(conv.id)}
									/>
								))}
							</div>
							<div className="p-3 border-t border-[var(--color-border)]">
								<Button
									variant="outline"
									className="w-full gap-2 text-xs h-8"
									onClick={createConversation}
									disabled={creating}
								>
									<Plus className="h-3.5 w-3.5" />
									New Conversation
								</Button>
							</div>
						</>
					)}
				</>
			) : (
				<div className="flex flex-col items-center gap-2 pt-2">
					<Button
						variant="ghost"
						size="icon"
						className="h-8 w-8"
						onClick={createConversation}
						disabled={creating || !user}
						title="New conversation"
					>
						<Plus className="h-4 w-4" />
					</Button>
				</div>
			)}
		</div>
	)
}
