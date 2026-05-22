/** Auth */

export interface User {
  id: string
  email: string
  role: string
}

export interface LoginResponse {
  token: string
  user: User
}

/** Conversations */

export interface MessageDto {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface ConversationDto {
  id: string
  current_cluster_snapshot_id: string | null
  messages: MessageDto[]
  created_at: string
}

export interface ConversationSummaryDto {
  id: string
  current_cluster_snapshot_id: string | null
  created_at: string
  preview: string | null
}

export interface SendMessageResponse {
  message: MessageDto
  cluster_snapshot_id: string
}

/** Cluster Snapshots */

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

/** Movies */

export interface MovieDto {
  id: number
  title: string
  release_year: number | null
  runtime: number | null
  vote_average: number | null
  vote_count: number | null
  bayesian_rating: number | null
  overview: string | null
  poster_url: string | null
  genres: string[]
  director: string | null
  top_cast: string[]
  original_language: string | null
  trailer_youtube_key: string | null
  umap_x: number | null
  umap_y: number | null
}

/** Scatter plot point enriched with cluster membership */

export interface ScatterPoint {
  movieId: number
  title: string
  clusterId: string
  clusterLabel: string | null
  x: number
  y: number
}

/** API errors */

export interface ApiError {
  detail: string
}
