import { apiClient } from '../client'
import type { ClusterSnapshotDto, UmapPointDto } from '../dto/snapshots'

/**
 * Fetch a cluster snapshot with its full cluster list and argmax members.
 *
 * @param snapshotId - Cluster snapshot UUID.
 * @returns ClusterSnapshotDto with clusters.
 */
export async function getSnapshotFetcher(snapshotId: string): Promise<ClusterSnapshotDto> {
    return apiClient<ClusterSnapshotDto>(`/cluster-snapshots/${snapshotId}`)
}

/**
 * Fetch UMAP 2D coordinates for all catalogued movies.
 * Used to render the uncoloured scatter plot silhouette before any clustering is performed.
 * The result is stable after ingest and can be cached indefinitely.
 *
 * @returns Array of UmapPointDto ordered by movie ID.
 */
export async function getAllUmapPointsFetcher(): Promise<UmapPointDto[]> {
    return apiClient<UmapPointDto[]>('/movies/umap-points')
}

/**
 * Delete a leaf cluster snapshot.
 *
 * @param snapshotId - Cluster snapshot UUID to delete.
 * @returns void
 */
export async function deleteSnapshotFetcher(snapshotId: string): Promise<void> {
    return apiClient<void>(`/cluster-snapshots/${snapshotId}`, { method: 'DELETE' })
}
