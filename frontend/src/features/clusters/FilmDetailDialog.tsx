import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useFetchMovieDetail } from "@/features/clusters/hooks/useFetchMovieDetail";
import { useUiStore } from "@/store/uiStore";
import { buildPosterUrl, formatRuntime, formatRating } from "@/features/clusters/utils/clusterFormatters";
import type { MovieDto } from "@/utils/types";

/**
 * Global film detail modal.
 *
 * Rendered once in SessionPage; opened by calling ``useUiStore.openFilmDetail(id)``.
 * Poster on the left, full metadata on the right. Skeleton placeholders while loading.
 */
export function FilmDetailDialog() {
  const { selectedMovieId, isFilmDetailOpen, closeFilmDetail } = useUiStore();
  const { data: film, isLoading } = useFetchMovieDetail(selectedMovieId);

  return (
    <Dialog open={isFilmDetailOpen} onOpenChange={(open) => !open && closeFilmDetail()}>
      <DialogContent className="max-w-2xl p-0 overflow-hidden gap-0">
        {isLoading || !film ? (
          <FilmSkeleton />
        ) : (
          <FilmLayout film={film} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function FilmSkeleton() {
  return (
    <div className="flex flex-col sm:flex-row">
      <Skeleton className="w-full sm:w-44 h-56 sm:h-auto shrink-0 rounded-none rounded-tl-lg rounded-tr-lg sm:rounded-tr-none sm:rounded-bl-lg" />
      <div className="flex-1 p-6 flex flex-col gap-3">
        <Skeleton className="h-6 w-3/4" />
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-2/5" />
        <Skeleton className="h-20 w-full mt-2" />
      </div>
    </div>
  );
}

function FilmLayout({ film }: { film: MovieDto }) {
  const posterSrc = buildPosterUrl(film.poster_url);
  const subtitle = [film.release_year, formatRuntime(film.runtime)].filter(Boolean).join(" · ");

  return (
    <div className="flex flex-col sm:flex-row min-h-[300px]">
      <div className="shrink-0 sm:w-44 bg-muted rounded-tl-lg rounded-tr-lg sm:rounded-tr-none sm:rounded-bl-lg overflow-hidden">
        {posterSrc ? (
          <img src={posterSrc} alt={film.title} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full min-h-[160px] flex items-center justify-center text-muted-foreground text-xs p-3 text-center">
            No poster
          </div>
        )}
      </div>

      <div className="flex-1 p-6 flex flex-col gap-2 overflow-y-auto max-h-[70vh] sm:max-h-[500px]">
        <h2 className="font-display text-xl leading-tight text-foreground">{film.title}</h2>

        {subtitle && (
          <p className="text-sm text-muted-foreground">{subtitle}</p>
        )}

        <div className="flex items-center gap-2 text-sm">
          {film.vote_average !== null && (
            <span className="text-primary font-medium">⭐ {formatRating(film.vote_average)}</span>
          )}
          {film.genres.length > 0 && (
            <span className="text-muted-foreground">{film.genres.slice(0, 3).join(", ")}</span>
          )}
        </div>

        {film.director && (
          <p className="text-sm text-muted-foreground">
            <span className="text-foreground/60 text-xs uppercase tracking-wider mr-1">Dir.</span>
            {film.director}
          </p>
        )}

        {film.top_cast.length > 0 && (
          <p className="text-sm text-muted-foreground">{film.top_cast.slice(0, 4).join(", ")}</p>
        )}

        {film.overview && (
          <p className="text-sm text-foreground/80 leading-relaxed mt-1">{film.overview}</p>
        )}
      </div>
    </div>
  );
}
