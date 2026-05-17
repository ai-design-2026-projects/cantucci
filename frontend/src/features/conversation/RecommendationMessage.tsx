import { motion } from "framer-motion";
import { useUiStore } from "@/store/uiStore";
import { Mascot } from "@/components/mascot/Mascot";
import { buildPosterUrl, formatRating } from "@/features/clusters/utils/clusterFormatters";
import type { RecommendationPayload } from "@/utils/types";

interface RecommendationMessageProps {
  recommendation: RecommendationPayload;
}

/**
 * Premium recommendation card rendered in place of a plain assistant bubble
 * when the turn carries a structured ``recommendation`` payload.
 *
 * Gold border-glow signals a convergence moment. Mascot aha pose sits in the
 * top-right corner. Films scroll horizontally — click any to open the detail
 * dialog.
 *
 * @param recommendation - Structured cluster + films payload from TurnResult.
 */
export function RecommendationMessage({ recommendation }: RecommendationMessageProps) {
  const { openFilmDetail } = useUiStore();
  const { cluster, films } = recommendation;

  return (
    <motion.div
      className="relative rounded-xl border border-primary/30 bg-bg-surface shadow-[0_0_24px_-4px_hsl(var(--primary)/0.18)] overflow-hidden"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
    >
      <div className="absolute top-3 right-3 z-10">
        <Mascot pose="aha" size={48} />
      </div>

      <div className="p-5 pr-16">
        <h3 className="font-display text-xl text-foreground tracking-tight leading-tight">
          {cluster.name}
        </h3>
        {cluster.description && (
          <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">
            {cluster.description}
          </p>
        )}
      </div>

      <div
        className="px-5 pb-5 flex gap-3 overflow-x-auto"
        style={{ scrollbarWidth: "thin" }}
      >
        {films.map((film) => {
          const posterSrc = buildPosterUrl(film.poster_url);
          return (
            <button
              key={film.id}
              type="button"
              onClick={() => openFilmDetail(film.id)}
              className="shrink-0 w-28 flex flex-col gap-1.5 text-left rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="w-28 h-40 rounded-md overflow-hidden bg-muted">
                {posterSrc ? (
                  <img
                    src={posterSrc}
                    alt={film.title}
                    className="w-full h-full object-cover hover:scale-105 transition-transform duration-300"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-muted-foreground text-xs p-2 text-center leading-tight">
                    {film.title}
                  </div>
                )}
              </div>
              <p className="text-xs font-medium text-foreground leading-tight line-clamp-2">
                {film.title}
              </p>
              <div className="flex items-center gap-1 text-[0.6875rem] text-muted-foreground">
                {film.release_year && <span>{film.release_year}</span>}
                {film.vote_average !== null && (
                  <>
                    {film.release_year && <span>·</span>}
                    <span>⭐ {formatRating(film.vote_average)}</span>
                  </>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </motion.div>
  );
}
