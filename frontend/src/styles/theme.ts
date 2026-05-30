/**
 * Derive a stable, maximally-distinguishable cluster color from an integer slot.
 *
 * Consecutive slots are spaced by the golden angle (≈137.508°) so that any two
 * distinct slots land as far apart as possible on the hue wheel, regardless of
 * how many clusters are shown.  The slot is persisted in the database and
 * inherited by carry-forward clusters, guaranteeing that an untouched cluster
 * keeps its color across operations.
 *
 * @param slot   - Stable integer color slot for the cluster (from ClusterDto.color_slot).
 * @param isDark - Whether the dark theme is active (adjusts lightness).
 * @returns HSL color string suitable for use in SVG, canvas, or CSS.
 */
export function clusterColorFromSlot(slot: number, isDark = false): string {
    const hue = (slot * 137.508) % 360
    const saturation = isDark ? 65 : 60
    const lightness = isDark ? 62 : 52
    return `hsl(${hue}, ${saturation}%, ${lightness}%)`
}
