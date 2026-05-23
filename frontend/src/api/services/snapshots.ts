import { apiClient } from '../client'
import type { ClusterSnapshotDto, ClusterSnapshotGraphDto } from '../dto/snapshots'

/**
 * Fetch a cluster snapshot with its full cluster list.
 *
 * @param snapshotId - Cluster snapshot UUID.
 * @returns ClusterSnapshotDto with clusters.
 */
export async function getSnapshotFetcher(snapshotId: string): Promise<ClusterSnapshotDto> {
    return apiClient<ClusterSnapshotDto>(`/cluster-snapshots/${snapshotId}`)
}

/**
 * Fetch all cluster snapshot nodes for a conversation as a DAG.
 *
 * @param conversationId - Conversation UUID.
 * @returns ClusterSnapshotGraphDto with all nodes.
 */
export async function getSnapshotGraphFetcher(conversationId: string): Promise<ClusterSnapshotGraphDto> {
    return apiClient<ClusterSnapshotGraphDto>(`/conversations/${conversationId}/cluster-snapshots`)
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
