import type { ScatterPoint } from '../hooks/useScatterData.ts'

/**
 * Single plotted point in the snapshot scatter chart.
 *
 * @param cx - SVG x coordinate.
 * @param cy - SVG y coordinate.
 * @param fill - Dot fill color.
 * @param payload - Scatter point payload.
 * @param onClusterClick - Called with the cluster ID when the dot is clicked.
 * @param dimmed - Whether the dot should be muted.
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
	return (
		<circle
			cx={cx}
			cy={cy}
			r={5}
			fill={fill}
			opacity={dimmed ? 0.2 : 0.85}
			stroke={fill}
			strokeWidth={1}
			style={{ cursor: 'pointer', transition: 'opacity 0.2s' }}
			onClick={() => payload && onClusterClick(payload.clusterId)}
		/>
	)
}
