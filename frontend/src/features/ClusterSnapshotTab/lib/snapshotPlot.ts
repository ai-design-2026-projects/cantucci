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

	let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity
	for (const point of points) {
		if (point.x < xMin) xMin = point.x
		if (point.x > xMax) xMax = point.x
		if (point.y < yMin) yMin = point.y
		if (point.y > yMax) yMax = point.y
	}
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