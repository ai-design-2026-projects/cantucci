import { fetchMovie } from "@/features/clusters/services/clusterService";
import type { ClusterDto, ClusterFilmStub, ClusterSnapshotPayload } from "@/utils/types";

/**
 * Convert persisted ClusterDto[] into ClusterSnapshotPayload[] by fetching
 * movie metadata for each top_titles entry in parallel.
 *
 * confidence is set to 0 — the confidence bar is hidden for settled snapshots,
 * so this value is never rendered.
 *
 * @param clusters - Persisted cluster data from SessionDto.cluster_snapshot.
 * @returns Hydrated snapshot payloads ready for the ClusterSnapshotStore.
 */
export async function hydrateClusterSnapshot(
  clusters: ClusterDto[],
): Promise<ClusterSnapshotPayload[]> {
  return Promise.all(
    clusters.map(async (cluster) => {
      const films = await Promise.all(
        cluster.top_titles.map((id) =>
          fetchMovie(id).then(
            (movie): ClusterFilmStub => ({
              id: movie.id,
              title: movie.title,
              poster_url: movie.poster_url,
              release_year: movie.release_year,
              vote_average: movie.vote_average,
            }),
          ),
        ),
      );
      const activeScores = cluster.soft_scores
        .filter((s) => !s.excluded)
        .map((s) => s.score);
      const confidence =
        activeScores.length > 0
          ? activeScores.reduce((sum, s) => sum + s, 0) / activeScores.length
          : 0;

      return {
        id: cluster.id,
        name: cluster.name,
        description: cluster.description,
        level: cluster.level,
        confidence,
        top_films: films,
      };
    }),
  );
}
