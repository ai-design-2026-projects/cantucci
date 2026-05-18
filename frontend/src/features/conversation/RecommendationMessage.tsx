import { useState } from "react";
import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import { TooltipProvider, Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { useUiStore } from "@/store/uiStore";
import { clusterColor, formatRating } from "@/features/clusters/utils/clusterFormatters";
import { RecommendationFilmsDialog } from "./RecommendationFilmsDialog";
import type { RecommendationPayload } from "@/utils/types";

interface RecommendationMessageProps {
  recommendation: RecommendationPayload;
}

/**
 * In-chat recommendation card rendered when the turn carries a structured
 * recommendation payload.
 *
 * Layout (top to bottom):
 * - Colored ribbon with cluster identity and "Your recommendation" label.
 * - Hero block: large poster for the first/key film with title, year, rating, overview.
 * - Cluster description (full, no truncation).
 * - Scrollable strip of remaining films.
 * - "View all N films" button opening a full-list Dialog.
 *
 * @param recommendation - Structured cluster + films payload from TurnDto.
 */
export function RecommendationMessage({ recommendation }: RecommendationMessageProps) {
  const { openFilmDetail } = useUiStore();
  const { cluster, films } = recommendation;
  const color = clusterColor(cluster.id.toString());
  const [dialogOpen, setDialogOpen] = useState(false);

  const heroFilm = films[0] ?? null;
  const restFilms = films.slice(1);

  return (
    <>
      <motion.div
        className="rounded-xl border border-border bg-card overflow-hidden"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <div
          className="flex items-center justify-between px-4 py-3 border-b border-border/50"
          style={{ backgroundColor: `${color}20` }}
        >
          <div className="flex items-center gap-2">
            <Sparkles className="w-3.5 h-3.5 shrink-0" style={{ color }} />
            <span className="font-display text-sm tracking-wide" style={{ color }}>
              Your recommendation
            </span>
          </div>
          <span className="text-xs text-muted-foreground truncate ml-4 max-w-[45%]">
            {cluster.name}
          </span>
        </div>

        <div className="p-4">
          {heroFilm && (
            <button
              type="button"
              onClick={() => openFilmDetail(heroFilm.id)}
              className="w-full flex gap-4 text-left rounded-lg hover:bg-accent/50 transition-colors p-2 -mx-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="shrink-0 w-28 h-40 rounded-md overflow-hidden bg-muted">
                {heroFilm.poster_url ? (
                  <img
                    src={heroFilm.poster_url}
                    alt={heroFilm.title}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-muted-foreground text-[0.6rem] p-2 text-center leading-tight">
                    {heroFilm.title}
                  </div>
                )}
              </div>
              <div className="flex-1 min-w-0 pt-1">
                <h3 className="font-display text-xl leading-tight tracking-tight text-foreground">
                  {heroFilm.title}
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {[
                    heroFilm.release_year,
                    heroFilm.vote_average !== null
                      ? `⭐ ${formatRating(heroFilm.vote_average)}`
                      : null,
                  ]
                    .filter(Boolean)
                    .join("  ·  ")}
                </p>
                {heroFilm.overview && (
                  <p className="mt-2 text-xs text-muted-foreground leading-relaxed line-clamp-4">
                    {heroFilm.overview}
                  </p>
                )}
              </div>
            </button>
          )}

          {cluster.description && (
            <p className="mt-3 text-sm text-muted-foreground leading-relaxed">
              {cluster.description}
            </p>
          )}

          {restFilms.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
                More from this cluster
              </p>
              <TooltipProvider delayDuration={300}>
                <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
                  {restFilms.map((film) => (
                    <Tooltip key={film.id}>
                      <TooltipTrigger asChild>
                        <button
                          type="button"
                          onClick={() => openFilmDetail(film.id)}
                          className="shrink-0 w-16 h-24 rounded-md overflow-hidden bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
                          <p className="text-muted-foreground text-xs">
                            ⭐ {formatRating(film.vote_average)}
                          </p>
                        )}
                      </TooltipContent>
                    </Tooltip>
                  ))}
                </div>
              </TooltipProvider>
            </div>
          )}

          {films.length > 0 && (
            <button
              type="button"
              onClick={() => setDialogOpen(true)}
              className="mt-4 w-full rounded-md border border-border/60 py-2 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              View all {films.length} films
            </button>
          )}
        </div>
      </motion.div>

      <RecommendationFilmsDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        films={films}
        clusterName={cluster.name}
      />
    </>
  );
}
