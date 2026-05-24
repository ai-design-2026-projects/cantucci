import { motion } from 'framer-motion'
import { Mascot } from '@/components/mascot'
import type { MessageDto } from '@/api/dto/conversations'

/**
 * Renders a single chat message bubble.
 * User messages appear on the right with primary color; assistant messages
 * on the left with a small Poppy avatar.
 *
 * @param message - MessageDto to render.
 * @returns Animated message bubble.
 */
export function MessageBubble({ message }: { message: MessageDto }) {
	const isUser = message.role === 'user'

	return (
		<motion.div
			className={`flex gap-2 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
			initial={{ opacity: 0, y: 8 }}
			animate={{ opacity: 1, y: 0 }}
			transition={{ duration: 0.2 }}
		>
			{!isUser && (
				<div className="flex-shrink-0 self-end">
					<Mascot expression="happy" size="sm" />
				</div>
			)}
			<div
				className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${isUser
						? 'bg-[var(--color-primary)] text-white rounded-br-sm'
						: 'bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text)] rounded-bl-sm'
					}`}
			>
				{message.content}
			</div>
		</motion.div>
	)
}
