import { Link } from 'react-router-dom'

/**
 * CinePal brand logo — small Poppy icon + app name in display font.
 *
 * @returns Anchor linking to the home page.
 */
export function BrandMark() {
	return (
		<Link to="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
			<span className="text-3xl font-display text-[var(--color-primary)]">CinePal</span>
		</Link>
	)
}
