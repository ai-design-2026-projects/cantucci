/**
 * TypeScript types mirroring the backend Pydantic DTOs.
 * These are the shapes returned by /sessions, /movies, and /auth endpoints.
 */

export type UserRole = "user" | "admin";

export interface User {
  id: string;
  email: string;
  role: UserRole;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export type StepType = "show" | "ask" | "stop";
export type SessionStatus = "active" | "converged" | "abandoned";

export interface ClusterFilmStub {
  id: number;
  title: string;
  poster_url: string | null;
  release_year: number | null;
  vote_average: number | null;
}

export interface ClusterSnapshotPayload {
  id: string;
  name: string;
  description: string | null;
  level: number;
  confidence: number;
  top_films: ClusterFilmStub[];
}

export interface RecommendationPayload {
  cluster: ClusterDto;
  films: MovieDto[];
}

export interface AmbiguityMeta {
  ui_format: "binary" | "forced_choice";
  cluster_refs: string[];
}

export interface TurnDto {
  turn_id: string;
  session_id: string;
  turn_number: number;
  user_message: string;
  assistant_message: string;
  step_type: StepType;
  converged: boolean;
  created_at: string;
  ambiguity_meta: AmbiguityMeta | null;
  recommendation: RecommendationPayload | null;
}

export interface SessionDto {
  session_id: string;
  status: SessionStatus;
  max_turns: number;
  created_at: string;
  updated_at: string;
  turn_count: number;
  first_user_message: string | null;
  cluster_snapshot: ClusterDto[];
  turns: TurnDto[];
}

export interface SoftScore {
  movie_id: number;
  score: number;
  excluded: boolean;
}

export interface ClusterDto {
  id: string;
  name: string;
  description: string | null;
  level: number;
  parent_cluster_id: string | null;
  soft_scores: SoftScore[];
  top_titles: number[];
}

export interface MovieDto {
  id: number;
  title: string;
  release_year: number | null;
  runtime: number | null;
  vote_average: number | null;
  vote_count: number | null;
  bayesian_rating: number | null;
  overview: string | null;
  poster_url: string | null;
  genres: string[];
  director: string | null;
  top_cast: string[];
  original_language: string | null;
}

