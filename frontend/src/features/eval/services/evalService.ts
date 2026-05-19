import { get } from "@/clients/apiClient";
import type { EvalSessionRow, MetricBundle, RunDetail, RunSummary } from "@/utils/types";

/**
 * List all eval runs, sorted newest-first.
 */
export function listRuns(): Promise<RunSummary[]> {
  return get<RunSummary[]>("/eval/runs");
}

/**
 * Fetch full run metadata plus overall aggregate metrics.
 *
 * @param runId - UUID of the run.
 */
export function getRunDetail(runId: string): Promise<RunDetail> {
  return get<RunDetail>(`/eval/runs/${runId}`);
}

/**
 * Fetch overall aggregate MetricBundle (with 95% CIs) for a run.
 *
 * @param runId - UUID of the run.
 */
export function getRunAggregate(runId: string): Promise<MetricBundle> {
  return get<MetricBundle>(`/eval/runs/${runId}/aggregate`);
}

/**
 * Fetch per-persona MetricBundles for a run.
 *
 * Returns a dict keyed by persona_id (or "__none__" for sessions without a persona).
 *
 * @param runId - UUID of the run.
 */
export function getRunAggregateByPersona(runId: string): Promise<Record<string, MetricBundle>> {
  return get<Record<string, MetricBundle>>(`/eval/runs/${runId}/aggregate/by-persona`);
}

/**
 * Fetch raw per-session eval metrics for a run (drill-down table data).
 *
 * @param runId - UUID of the run.
 */
export function getRunSessions(runId: string): Promise<EvalSessionRow[]> {
  return get<EvalSessionRow[]>(`/eval/runs/${runId}/sessions`);
}
