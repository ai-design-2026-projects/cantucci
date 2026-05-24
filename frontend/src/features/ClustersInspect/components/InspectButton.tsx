import { LayoutGrid } from 'lucide-react'
import { Button } from '@/components/button'

/**
 * Button that opens the cluster inspect modal.
 *
 * @param onClick  - Handler to open the inspect dialog.
 * @param disabled - Disables the button when no snapshot is active.
 * @returns Ghost icon button with label.
 */
export function InspectButton({
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
			<LayoutGrid className="h-4 w-4" />
			<span className="hidden sm:inline text-xs">Inspect</span>
		</Button>
	)
}