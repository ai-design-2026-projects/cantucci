import type { ScatterPoint } from '../hooks/useScatterData.ts'

/**
 * Single plotted point in the snapshot scatter chart.
 *
 * Opacity is driven by the argmax soft-membership probability at all times
 * (not gated on cluster selection). Exemplar movies always render at a
 * larger radius. When `dimmed` is true (the dot belongs to a non-selected
 * cluster), opacity collapses to 0.15 regardless of probability.
 *
 * Click events stop propagation so they do not bubble to the chart background
 * handler (which clears the selection).
 *
 * @param cx - SVG x coordinate.
 * @param cy - SVG y coordinate.
 * @param fill - Dot fill color.
 * @param payload - Scatter point payload.
 * @param onClusterClick - Called with the cluster ID when the dot is clicked.
 * @param dimmed - Whether the dot should be muted (belongs to a non-selected cluster).
 * @returns Clickable SVG circle.
 */
export function CustomDot({
    cx = 0,
    cy = 0,
    fill = '#ccc',
    payload,
    onClusterClick,
    dimmed,
}: {
    cx?: number
    cy?: number
    fill?: string
    payload?: ScatterPoint
    onClusterClick: (clusterId: string | null) => void
    dimmed: boolean
}) {
    const prob = payload?.probability ?? 0.7
    const opacity = dimmed ? 0.15 : Math.min(1, 0.25 + 0.75 * prob)
    const r = payload?.isExemplar ? 9 : 5

    return (
        <circle
            cx={cx}
            cy={cy}
            r={r}
            fill={fill}
            opacity={opacity}
            stroke={fill}
            strokeWidth={1}
            style={{ cursor: 'pointer', transition: 'opacity 0.2s' }}
            onClick={(e) => {
                e.stopPropagation()
                payload && onClusterClick(payload.clusterId)
            }}
        />
    )
}
