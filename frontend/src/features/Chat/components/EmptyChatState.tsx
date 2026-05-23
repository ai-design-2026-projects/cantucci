import { Mascot } from '@/components/mascot'

/**
 * Placeholder shown inside an empty conversation before the first message.
 *
 * @returns Empty state with medium Poppy and instructional copy.
 */
export function EmptyChatState() {
	return (
		<div className="flex flex-col items-center justify-center h-full gap-4 text-center px-8">
			<Mascot expression="sleepy" size="md" />
			<p className="text-base font-display text-[var(--color-text)]">
				Ask Poppy anything about your catalogue
			</p>
			<p className="text-sm text-[var(--color-muted)] max-w-xs leading-relaxed">
				Try: "Group action movies separately" or "Merge the two sci-fi clusters"
			</p>
		</div>
	)
}
