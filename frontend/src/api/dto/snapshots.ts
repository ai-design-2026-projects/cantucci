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
