export interface UmapPointDto {
    movie_id: number
    title: string
    umap_x: number
    umap_y: number
}

export interface ClusterDto {
    id: string
    label: string | null
    summary: string | null
    exemplar_movie_ids: number[]
    parent_cluster_id: string | null
    color_slot: number
}

export interface ClusterMembershipDto {
    movie_id: number
    probability: number
}

export interface SnapshotMemberDto {
    movie_id: number
    title: string
    umap_x: number
    umap_y: number
    cluster_id: string
    probability: number
}

export interface ClusterSnapshotDto {
    id: string
    parent_id: string | null
    operation: string
    params: Record<string, unknown>
    config_hash: string
    clusters: ClusterDto[]
    members: SnapshotMemberDto[]
    created_at: string
}

export interface ClusterSnapshotGraphNode {
    id: string
    parent_id: string | null
    operation: string
    created_at: string
    params: Record<string, unknown>
    resolved_cluster_labels: Record<string, string>
}

export interface ClusterSnapshotGraphDto {
    cluster_snapshots: ClusterSnapshotGraphNode[]
}
