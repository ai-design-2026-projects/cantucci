import { AnimatePresence, motion } from 'framer-motion'
import { Mascot } from '@/components/mascot'
import { useLoadingStatusRotation } from '../hooks/useLoadingStatusRotation'

/**
 * Fixed-size loading bubble shown while a turn is in flight.
 * Displays a rotating status message and animated Poppy mascot.
 * The bubble dimensions never change regardless of content.
 *
 * @param isLoading - Controls whether the bubble is visible.
 * @param isError   - When true, Poppy shows a sad expression.
 * @returns Animated loading bubble or null when not loading.
 */
export function LoadingBubble({
	isLoading,
	isError,
}: {
	isLoading: boolean
	isError: boolean
}) {
	const { message, expression } = useLoadingStatusRotation(isLoading, isError)

	return (
		<AnimatePresence>
			{isLoading && (
				<motion.div
					className="flex flex-row gap-2"
					initial={{ opacity: 0, y: 8 }}
					animate={{ opacity: 1, y: 0 }}
					exit={{ opacity: 0, y: 8 }}
					transition={{ duration: 0.2 }}
				>
					<div className="flex-shrink-0 self-end">
						<Mascot expression={expression} size="sm" />
					</div>
					{/* Fixed size — must not resize based on content */}
					<div className="w-64 h-16 flex items-center px-4 rounded-2xl rounded-bl-sm bg-[var(--color-surface)] border border-[var(--color-border)] overflow-hidden">
						<AnimatePresence mode="wait">
							<motion.span
								key={message}
								className="text-sm text-[var(--color-muted)] leading-tight"
								initial={{ opacity: 0 }}
								animate={{ opacity: 1 }}
								exit={{ opacity: 0 }}
								transition={{ duration: 0.3 }}
							>
								{message}
							</motion.span>
						</AnimatePresence>
					</div>
				</motion.div>
			)}
		</AnimatePresence>
	)
}
