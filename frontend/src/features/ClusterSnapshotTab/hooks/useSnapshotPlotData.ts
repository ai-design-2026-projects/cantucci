import { useMemo } from 'react'
import type { ClusterSnapshotDto } from '@/api/dto/snapshots'
import type { ScatterPoint } from './useScatterData.ts'
import { computeScatterDomains, groupScatterPointsByCluster } from '../lib/snapshotPlot.ts'

/**
 * Derives chart domains and cluster buckets for the snapshot plot.
 *
 * @param points - Scatter points rendered in the plot.
 * @param snapshot - Active cluster snapshot.
 * @param baseDomain - Optional base silhouette domain.
 * @returns Computed domains and clustered scatter points.
 */
export function useSnapshotPlotData(
	points: ScatterPoint[],
	snapshot: ClusterSnapshotDto,
	baseDomain?: { x: [number, number]; y: [number, number] },
) {
	const perSnapshotDomain = useMemo(() => computeScatterDomains(points), [points])
	const byCluster = useMemo(() => groupScatterPointsByCluster(snapshot, points), [points, snapshot])

	return {
		xDomain: baseDomain?.x ?? perSnapshotDomain.xDomain,
		yDomain: baseDomain?.y ?? perSnapshotDomain.yDomain,
		byCluster,
	}
}