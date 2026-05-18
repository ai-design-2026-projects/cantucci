import { TooltipProvider, Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { useUiStore } from "@/store/uiStore";
import { ConfidenceBar } from "@/components/ConfidenceBar";
import { buildPosterUrl, clusterColor } from "@/features/clusters/utils/clusterFormatters";
import type { ClusterSnapshotPayload } from "@/utils/types";

interface ClusterCardProps {
  cluster: ClusterSnapshotPayload;
  isRefining: boolean;
}

/**
 * Card for a single cluster snapshot entry in the side panel.
 *
 * Left color stripe is deterministically derived from the cluster UUID so it
 * stays stable across refinement cycles. A shimmer overlay pulses while the
 * turn is still in-flight.
 *
 * @param cluster - Snapshot payload from the NDJSON stream.
 * @param isRefining - True while the turn is in-flight; shows shimmer.
 */
export function ClusterCard({ cluster, isRefining }: ClusterCardProps) {
  const { openFilmDetail } = useUiStore();
  const color = clusterColor(cluster.id);

  return (
    <div className="relative rounded-lg border border-border bg-card overflow-hidden">
      <div className="absolute left-0 top-0 bottom-0 w-1 shrink-0" style={{ backgroundColor: color }} />

      {isRefining && (
        <div className="absolute inset-0 z-10 pointer-events-none overflow-hidden rounded-lg">
          <div
            className="absolute inset-0 animate-shimmer"
            style={{
              background: "linear-gradient(90deg, transparent 25%, rgba(255,255,255,0.06) 50%, transparent 75%)",
              backgroundSize: "200% 100%",
            }}
          />
        </div>
      )}

      <div className="pl-5 pr-4 pt-4 pb-3">
        <h4 className="font-display text-base text-foreground tracking-tight leading-tight">
          {cluster.name}
        </h4>
        {cluster.description && (
          <p className="mt-0.5 text-xs text-muted-foreground leading-relaxed">
            {cluster.description}
          </p>
        )}

        <div className="mt-2">
          <ConfidenceBar score={cluster.confidence} label={`${cluster.name} confidence`} />
        </div>

        {cluster.top_films.length > 0 && (
          <TooltipProvider delayDuration={300}>
            <div className="mt-3 flex gap-1.5 overflow-x-auto pb-1 -mx-1 px-1">
              {cluster.top_films.map((film) => (
                <Tooltip key={film.id}>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={() => openFilmDetail(film.id)}
                      className="shrink-0 w-12 h-[72px] rounded overflow-hidden bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {buildPosterUrl(film.poster_url) ? (
                        <img
                          src={buildPosterUrl(film.poster_url)!}
                          alt={film.title}
                          className="w-full h-full object-cover hover:scale-110 transition-transform duration-200"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-muted-foreground text-[0.5rem] p-1 text-center leading-tight">
                          {film.title}
                        </div>
                      )}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom">
                    <p className="font-medium">{film.title}</p>
                    {film.release_year && (
                      <p className="text-muted-foreground text-xs">{film.release_year}</p>
                    )}
                  </TooltipContent>
                </Tooltip>
              ))}
            </div>
          </TooltipProvider>
        )}
      </div>
    </div>
  );
}
