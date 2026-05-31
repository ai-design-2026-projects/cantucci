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
export function groupScatterPointsByCluster(snapshot: ClusterSnapshotDto | undefined, points: ScatterPoint[]) {
    if (!snapshot) return {}
    return snapshot.clusters.reduce<Record<string, ScatterPoint[]>>((accumulator, cluster) => {
        accumulator[cluster.id] = points.filter((point) => point.clusterId === cluster.id)
        return accumulator
    }, {})
}

/**
 * Computes the probability-weighted centroid for every cluster in a snapshot.
 *
 * For each cluster, walks the snapshot members whose argmax cluster is that
 * cluster and accumulates `Σ p*x / Σ p, Σ p*y / Σ p` using the argmax
 * membership probability as the weight. Clusters with no members or zero
 * total weight are omitted.
 *
 * @param snapshot - Active cluster snapshot (provides cluster list and members).
 * @returns Array of `{ clusterId, x, y }` centroids, one per non-empty cluster.
 */
export function computeClusterCentroids(
    snapshot: ClusterSnapshotDto,
): Array<{ clusterId: string; x: number; y: number }> {
    const result: Array<{ clusterId: string; x: number; y: number }> = []

    for (const cluster of snapshot.clusters) {
        let sumW = 0, sumX = 0, sumY = 0
        for (const m of snapshot.members) {
            if (m.cluster_id !== cluster.id) continue
            sumW += m.probability
            sumX += m.probability * m.umap_x
            sumY += m.probability * m.umap_y
        }
        if (sumW === 0) continue
        result.push({ clusterId: cluster.id, x: sumX / sumW, y: sumY / sumW })
    }

    return result
}
