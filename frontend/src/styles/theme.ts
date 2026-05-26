/**
 * Resolve the UUID to use when coloring a cluster.
 *
 * For focus snapshots the focused cluster carries the source cluster's id as
 * parent_cluster_id, so we color by the parent — keeping the same hue as the
 * previous turn. For all other operations, the cluster colors by its own id.
 *
 * @param operation - Snapshot operation string (e.g. "focus", "drill_down").
 * @param cluster   - Cluster DTO with id and parent_cluster_id.
 * @returns UUID string to pass to clusterColorFromUuid.
 */
export function clusterColorKey(
    operation: string,
    cluster: { id: string; parent_cluster_id: string | null },
): string {
    return operation === 'focus' && cluster.parent_cluster_id
        ? cluster.parent_cluster_id
        : cluster.id
}

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
