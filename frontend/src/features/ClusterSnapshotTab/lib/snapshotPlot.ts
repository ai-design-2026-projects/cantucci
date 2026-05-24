import type { ClusterSnapshotDto } from '@/api/dto/snapshots'
import type { ScatterPoint } from '../hooks/useScatterData.ts'

/**
 * Computes the padded axis domains for a scatter plot.
 *
 * @param points - Scatter points rendered in the chart.
 * @returns X and Y domains with a small margin.
 */
export function computeScatterDomains(points: ScatterPoint[]) {
	if (points.length === 0) {
		return { xDomain: [0, 1] as [number, number], yDomain: [0, 1] as [number, number] }
	}

	const xs = points.map((point) => point.x)
	const ys = points.map((point) => point.y)
	const xMin = Math.min(...xs)
	const xMax = Math.max(...xs)
	const yMin = Math.min(...ys)
	const yMax = Math.max(...ys)
	const xPad = (xMax - xMin) * 0.05 || 1
	const yPad = (yMax - yMin) * 0.05 || 1

	return {
		xDomain: [xMin - xPad, xMax + xPad] as [number, number],
		yDomain: [yMin - yPad, yMax + yPad] as [number, number],
	}
}

/**
 * Groups scatter points by cluster ID.
 *
 * @param snapshot - Active cluster snapshot.
 * @param points - Scatter points rendered in the chart.
 * @returns Map-like record keyed by cluster ID.
 */
export function groupScatterPointsByCluster(snapshot: ClusterSnapshotDto, points: ScatterPoint[]) {
	return snapshot.clusters.reduce<Record<string, ScatterPoint[]>>((accumulator, cluster) => {
		accumulator[cluster.id] = points.filter((point) => point.clusterId === cluster.id)
		return accumulator
	}, {})
}