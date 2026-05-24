import { clsx, type ClassValue } from 'clsx'

/**
 * Merge class names, resolving Tailwind conflicts.
 *
 * @param inputs - Class name fragments or conditional class maps.
 * @returns Merged class name string.
 */
export function cn(...inputs: ClassValue[]): string {
	return clsx(inputs)
}

/**
 * Clamp a number between min and max.
 *
 * @param value - Number to clamp.
 * @param min   - Lower bound.
 * @param max   - Upper bound.
 * @returns Clamped value.
 */
export function clamp(value: number, min: number, max: number): number {
	return Math.max(min, Math.min(max, value))
}

/**
 * Format an ISO datetime string as a relative human-readable label.
 * Falls back to locale date string for old dates.
 *
 * @param iso - ISO 8601 datetime string.
 * @returns Relative time label like "2 hours ago" or "May 10".
 */
export function relativeTime(iso: string): string {
	const date = new Date(iso)
	const now = Date.now()
	const diff = now - date.getTime()
	const minutes = Math.floor(diff / 60_000)
	if (minutes < 1) return 'just now'
	if (minutes < 60) return `${minutes}m ago`
	const hours = Math.floor(minutes / 60)
	if (hours < 24) return `${hours}h ago`
	const days = Math.floor(hours / 24)
	if (days < 7) return `${days}d ago`
	return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
