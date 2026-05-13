import { useUiStore } from "@/store/uiStore";
import { useSessionHandler } from "@/features/session/hooks/useSessionHandler";
import { useClusterStore } from "@/store/clusterStore";

/**
 * Handlers for the post-convergence reveal screen interactions.
 *
 * @returns Object with selectMovie, closeDetail, and restartSession handlers.
 */
export function useRevealHandler() {
  const { openFilmDetail, closeFilmDetail } = useUiStore();
  const { setConvergedCluster } = useClusterStore();
  const { restartSession } = useSessionHandler();

  /**
   * Open the film detail modal for the given movie id.
   *
   * @param movieId - TMDB integer movie id.
   */
  function selectMovie(movieId: number) {
    openFilmDetail(movieId);
  }

  /**
   * Close the film detail modal and clear the selected movie.
   */
  function closeDetail() {
    closeFilmDetail();
  }

  return { selectMovie, closeDetail, restartSession, setConvergedCluster };
}
