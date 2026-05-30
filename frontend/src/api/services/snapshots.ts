import { apiClient } from '../client'
import type { ClusterSnapshotDto } from '../dto/snapshots'

/**
 * Fetch a cluster snapshot with its full cluster list and argmax members.
 *
 * @param snapshotId - Cluster snapshot UUID.
 * @returns ClusterSnapshotDto with clusters.
 */
export async function getSnapshotFetcher(snapshotId: string): Promise<ClusterSnapshotDto> {
    return apiClient<ClusterSnapshotDto>(`/cluster-snapshots/get/${snapshotId}`)
}

/**
 * Fetch the most recent root (base HDBSCAN) cluster snapshot.
 * Returns 404 if no snapshot has been ingested yet.
 *
 * @returns ClusterSnapshotDto for the root snapshot.
 */
export async function getRootSnapshotFetcher(): Promise<ClusterSnapshotDto> {
    return apiClient<ClusterSnapshotDto>('/cluster-snapshots/get_root')
}

/**
 * Delete a leaf cluster snapshot.
 *
 * @param snapshotId - Cluster snapshot UUID to delete.
 * @returns void
 */
export async function deleteSnapshotFetcher(snapshotId: string): Promise<void> {
    return apiClient<void>(`/cluster-snapshots/delete/${snapshotId}`, { method: 'DELETE' })
}
