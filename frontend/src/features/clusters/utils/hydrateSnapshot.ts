import { fetchMovie } from "@/features/clusters/services/clusterService";
import type { ClusterDto, ClusterFilmStub, ClusterSnapshotPayload } from "@/utils/types";

/**
 * Convert persisted ClusterDto[] into ClusterSnapshotPayload[] by fetching
 * movie metadata for each assignment in soft_scores.
 *
 * Ordering mirrors the live snapshot: non-excluded films first (score desc),
 * then excluded. Using soft_scores ensures all films are present even for
 * sessions saved before the top_titles cap was removed.
 *
 * @param clusters - Persisted cluster data from SessionDto.cluster_snapshot.
 * @returns Hydrated snapshot payloads ready for the ClusterSnapshotStore.
 */
export async function hydrateClusterSnapshot(
  clusters: ClusterDto[],
): Promise<ClusterSnapshotPayload[]> {
  return Promise.all(
    clusters.map(async (cluster) => {
      const ordered = [...cluster.soft_scores].sort((a, b) => {
        if (a.excluded !== b.excluded) return a.excluded ? 1 : -1;
        return b.score - a.score;
      });

      const films = await Promise.all(
        ordered.map((s) =>
          fetchMovie(s.movie_id).then(
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
        films,
      };
    }),
  );
}
