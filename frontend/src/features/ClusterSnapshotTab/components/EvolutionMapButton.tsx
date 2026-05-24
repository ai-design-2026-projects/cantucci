import { GitBranch } from 'lucide-react'
import { Button } from '@/components/button'

/**
 * Button that opens the cluster snapshot evolution map modal.
 *
 * @param onClick   - Handler to open the evolution map dialog.
 * @param disabled  - Disables the button when no conversation is active.
 * @returns Ghost icon button with label.
 */
export function EvolutionMapButton({
	onClick,
	disabled,
}: {
	onClick: () => void
	disabled?: boolean
}) {
	return (
		<Button
			variant="ghost"
			size="sm"
			onClick={onClick}
			disabled={disabled}
			className="gap-1.5"
		>
			<GitBranch className="h-4 w-4" />
			<span className="hidden sm:inline text-xs">Evolution</span>
		</Button>
	)
}
