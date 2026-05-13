import { useQuery } from "@tanstack/react-query";
import { fetchConvergedCluster } from "@/features/clusters/services/clusterService";
import type { ConvergedClusterPublic } from "@/utils/types";

/**
 * Fetch the converged cluster for a session.
 *
 * Only fires when ``enabled`` is true (i.e. after convergence is signalled).
 *
 * @param sessionId - UUID of the session.
 * @param enabled - Whether to run the query. Pass ``true`` only when converged.
 * @returns TanStack Query result with ConvergedClusterPublic.
 */
export function useFetchConvergedCluster(sessionId: string | null, enabled: boolean) {
  return useQuery<ConvergedClusterPublic, Error>({
    queryKey: ["converged-cluster", sessionId],
    queryFn: () => fetchConvergedCluster(sessionId!),
    enabled: enabled && sessionId !== null,
    staleTime: Infinity,
  });
}
