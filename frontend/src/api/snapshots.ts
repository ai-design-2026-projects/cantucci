import { apiClient } from './client'

export interface ClusterDto {
  id: string
  label: string | null
  summary: string | null
  exemplar_movie_ids: number[]
  parent_cluster_id: string | null
  size: number
}

export interface ClusterSnapshotDto {
  id: string
  parent_id: string | null
  operation: string
  params: Record<string, unknown>
  config_hash: string
  clusters: ClusterDto[]
  created_at: string
}

export interface ClusterSnapshotGraphNode {
  id: string
  parent_id: string | null
  operation: string
  created_at: string
}

export interface ClusterSnapshotGraphDto {
  cluster_snapshots: ClusterSnapshotGraphNode[]
}

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
