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

// ── Eval Lab types (mirrors backend/routers/dtos.py eval DTOs) ──────────────

export interface MetricCI {
  value: number;
  ci_lo: number;
  ci_hi: number;
  n: number;
}

export interface MetricBundle {
  precision_at_k: MetricCI;
  recall_at_k: MetricCI;
  ndcg_at_k: MetricCI;
  turns_to_convergence: MetricCI;
  avg_cognitive_load: MetricCI;
  total_cost_usd: MetricCI;
  drift_events: MetricCI;
  converged_rate: MetricCI;
  explicit_acceptance_rate: MetricCI;
  judge_clustering_coherence: MetricCI;
  judge_question_quality: MetricCI;
  judge_profile_fidelity: MetricCI;
}

export type RunStatus = "running" | "completed" | "aborted";
export type RunCondition =
  | "baseline"
  | "uncertainty"
  | "random"
  | "boundary"
  | "popularity"
  | "component_test"
  | "human";

export interface RunSummary {
  id: string;
  name: string;
  condition: RunCondition;
  status: RunStatus;
  started_at: string | null;
  ended_at: string | null;
  n_sessions: number;
}

export interface RunDetail {
  id: string;
  name: string;
  condition: RunCondition;
  config_hash: string;
  seed: number;
  model_version: string;
  status: RunStatus;
  notes: string | null;
  started_at: string | null;
  ended_at: string | null;
  n_sessions: number;
  aggregate: MetricBundle;
  config_snapshot?: Record<string, unknown>;
}

export interface EvalSessionRow {
  session_id: string;
  persona_id: string | null;
  ground_truth_id: string | null;
  converged: boolean;
  explicit_acceptance: boolean;
  turns_to_convergence: number | null;
  avg_cognitive_load: number | null;
  total_cost_usd: number;
  drift_events: number;
  precision_at_k: number | null;
  recall_at_k: number | null;
  ndcg_at_k: number | null;
  judge_clustering_coherence: number | null;
  judge_question_quality: number | null;
  judge_profile_fidelity: number | null;
}

export interface RunFilters {
  name: string;
  condition: RunCondition | "";
  status: RunStatus | "";
  dateFrom: string;
  dateTo: string;
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

