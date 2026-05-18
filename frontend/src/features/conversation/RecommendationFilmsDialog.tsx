import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useUiStore } from "@/store/uiStore";
import { formatRating } from "@/features/clusters/utils/clusterFormatters";
import type { MoviePublic } from "@/utils/types";

interface RecommendationFilmsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  films: MoviePublic[];
  clusterName: string;
}

/**
 * Modal listing all films in a recommendation cluster.
 *
 * Opens from the "View all N films" button inside RecommendationMessage.
 * Clicking a film card opens the FilmDetailDialog via the UI store.
 *
 * @param open - Controlled open state.
 * @param onOpenChange - Called when the dialog should open or close.
 * @param films - Full list of films in the recommendation payload.
 * @param clusterName - Name of the cluster, shown as the dialog title.
 */
export function RecommendationFilmsDialog({
  open,
  onOpenChange,
  films,
  clusterName,
}: RecommendationFilmsDialogProps) {
  const { openFilmDetail } = useUiStore();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl p-0 overflow-hidden gap-0">
        <DialogHeader className="px-6 pt-6 pb-4 border-b border-border">
          <DialogTitle className="font-display text-lg">{clusterName}</DialogTitle>
          <DialogDescription>All {films.length} films in this cluster</DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[65vh]">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 p-6">
            {films.map((film) => (
              <button
                key={film.id}
                type="button"
                onClick={() => {
                  openFilmDetail(film.id);
                  onOpenChange(false);
                }}
                className="text-left rounded-md overflow-hidden border border-border bg-card hover:bg-accent transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <div className="aspect-[2/3] w-full bg-muted">
                  {film.poster_url ? (
                    <img
                      src={film.poster_url}
                      alt={film.title}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-muted-foreground text-[0.55rem] p-2 text-center leading-tight">
                      {film.title}
                    </div>
                  )}
                </div>
                <div className="p-2">
                  <p className="text-xs font-medium leading-tight line-clamp-2">{film.title}</p>
                  <p className="text-[0.6rem] text-muted-foreground mt-0.5">
                    {[
                      film.release_year,
                      film.vote_average !== null
                        ? `⭐ ${formatRating(film.vote_average)}`
                        : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
              </button>
            ))}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
