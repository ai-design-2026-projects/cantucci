import { Link } from 'react-router-dom'
import { Mascot } from '@/components/mascot/Mascot'

/**
 * CinePal brand logo — small Poppy icon + app name in display font.
 *
 * @returns Anchor linking to the home page.
 */
export function BrandMark() {
  return (
    <Link to="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
      <Mascot expression="happy" size="sm" />
      <span className="text-xl font-display text-[var(--color-text)]">CinePal</span>
    </Link>
  )
}
