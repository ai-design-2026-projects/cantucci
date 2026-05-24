/**
 * Derive a stable cluster color from a UUID string by hashing its characters
 * to a hue value, then applying fixed saturation/lightness tuned to each theme.
 *
 * @param uuid - Cluster UUID string.
 * @param isDark - Whether the dark theme is active (adjusts lightness).
 * @returns HSL color string suitable for use in SVG, canvas, or CSS.
 */
export function clusterColorFromUuid(uuid: string, isDark = false): string {
	let hash = 0
	for (let i = 0; i < uuid.length; i++) {
		hash = (hash * 31 + uuid.charCodeAt(i)) >>> 0
	}
	const hue = hash % 360
	const saturation = isDark ? 65 : 60
	const lightness = isDark ? 62 : 52
	return `hsl(${hue}, ${saturation}%, ${lightness}%)`
}
