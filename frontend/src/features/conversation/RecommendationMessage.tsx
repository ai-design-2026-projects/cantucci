import { motion } from "framer-motion";
import { TooltipProvider, Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { useUiStore } from "@/store/uiStore";
import { clusterColor, formatRating } from "@/features/clusters/utils/clusterFormatters";
import type { RecommendationPayload } from "@/utils/types";

interface RecommendationMessageProps {
  recommendation: RecommendationPayload;
}

/**
 * In-chat recommendation card rendered when the turn carries a structured
 * ``recommendation`` payload.
 *
 * Visually matches the right-panel ``ClusterCard``: left color stripe derived
 * from the cluster UUID, cluster name + description, and a grid of film poster
 * thumbnails with click-to-open detail.
 *
 * @param recommendation - Structured cluster + films payload from TurnResult.
 */
export function RecommendationMessage({ recommendation }: RecommendationMessageProps) {
  const { openFilmDetail } = useUiStore();
  const { cluster, films } = recommendation;
  const color = clusterColor(cluster.id);

  return (
    <motion.div
      className="flex flex-col gap-2"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
    >
      <p className="text-sm font-medium text-muted-foreground tracking-wide uppercase px-0.5">
        Here are your recommendations
      </p>

      <div className="relative rounded-lg border border-border bg-card overflow-hidden">
      <div className="absolute left-0 top-0 bottom-0 w-1 shrink-0" style={{ backgroundColor: color }} />

      <div className="pl-5 pr-4 pt-4 pb-3">
        <h3 className="font-display text-base text-foreground tracking-tight leading-tight">
          {cluster.name}
        </h3>
        {cluster.description && (
          <p className="mt-0.5 text-xs text-muted-foreground leading-relaxed line-clamp-2">
            {cluster.description}
          </p>
        )}

        {films.length > 0 && (
          <TooltipProvider delayDuration={300}>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {films.slice(0, 8).map((film) => (
                <Tooltip key={film.id}>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={() => openFilmDetail(film.id)}
                      className="shrink-0 w-12 h-[72px] rounded overflow-hidden bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {film.poster_url ? (
                        <img
                          src={film.poster_url}
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
                    {film.vote_average !== null && (
                      <p className="text-muted-foreground text-xs">⭐ {formatRating(film.vote_average)}</p>
                    )}
                  </TooltipContent>
                </Tooltip>
              ))}
            </div>
          </TooltipProvider>
        )}
      </div>
      </div>
    </motion.div>
  );
}
