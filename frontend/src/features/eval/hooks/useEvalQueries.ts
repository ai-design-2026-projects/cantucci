import { useQuery } from "@tanstack/react-query";
import {
  getRunAggregate,
  getRunAggregateByPersona,
  getRunDetail,
  getRunSessions,
  listRuns,
} from "@/features/eval/services/evalService";

/**
 * Fetch all eval runs (list for the sidebar).
 */
export function useRuns() {
  return useQuery({
    queryKey: ["eval", "runs"],
    queryFn: listRuns,
  });
}

/**
 * Fetch full run metadata + overall aggregate for the selected run.
 *
 * @param runId - UUID of the selected run, or null when none selected.
 */
export function useRunDetail(runId: string | null) {
  return useQuery({
    queryKey: ["eval", "runs", runId, "detail"],
    queryFn: () => getRunDetail(runId!),
    enabled: runId !== null,
  });
}

/**
 * Fetch overall aggregate MetricBundle (with 95% CIs) for a run.
 *
 * @param runId - UUID of the selected run, or null when none selected.
 */
export function useRunAggregate(runId: string | null) {
  return useQuery({
    queryKey: ["eval", "runs", runId, "aggregate"],
    queryFn: () => getRunAggregate(runId!),
    enabled: runId !== null,
  });
}

/**
 * Fetch per-persona MetricBundles for a run.
 *
 * @param runId - UUID of the selected run, or null when none selected.
 */
export function useRunAggregateByPersona(runId: string | null) {
  return useQuery({
    queryKey: ["eval", "runs", runId, "aggregate", "by-persona"],
    queryFn: () => getRunAggregateByPersona(runId!),
    enabled: runId !== null,
  });
}

/**
 * Fetch per-session eval metric rows for the drill-down table.
 *
 * @param runId - UUID of the selected run, or null when none selected.
 */
export function useRunSessions(runId: string | null) {
  return useQuery({
    queryKey: ["eval", "runs", runId, "sessions"],
    queryFn: () => getRunSessions(runId!),
    enabled: runId !== null,
  });
}
