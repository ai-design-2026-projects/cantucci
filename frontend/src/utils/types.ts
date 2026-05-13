/**
 * TypeScript types mirroring the backend Pydantic DTOs.
 * These are the shapes returned by /sessions and /movies endpoints.
 */

export type StepType = "show" | "ask" | "stop";
export type SessionStatus = "active" | "converged" | "abandoned";

export interface AmbiguityMeta {
  ui_format: "binary" | "forced_choice";
  cluster_refs: string[];
}

export interface TurnResult {
  turn_id: string;
  session_id: string;
  turn_number: number;
  user_message: string;
  assistant_message: string;
  step_type: StepType;
  converged: boolean;
  created_at: string;
  ambiguity_meta: AmbiguityMeta | null;
}

export interface SessionState {
  session_id: string;
  status: SessionStatus;
  max_turns: number;
  created_at: string;
  updated_at: string;
  turns: TurnResult[];
}

export interface SoftScore {
  movie_id: number;
  score: number;
  excluded: boolean;
}

export interface ClusterPublic {
  id: string;
  name: string;
  description: string | null;
  level: number;
  parent_cluster_id: string | null;
  soft_scores: SoftScore[];
  top_titles: number[];
}

export interface MoviePublic {
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

export interface ConvergedClusterPublic {
  cluster: ClusterPublic;
  movies: MoviePublic[];
  preference_profile: Record<string, unknown> | null;
}
