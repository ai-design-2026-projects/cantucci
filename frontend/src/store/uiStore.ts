import { create } from "zustand";

interface UiStore {
  /** TMDB movie id of the film currently open in the detail modal. */
  selectedMovieId: number | null;
  /** Whether the film detail modal is open. */
  isFilmDetailOpen: boolean;
  /** Whether the one-shot cinematic reveal animation is playing. */
  isRevealPlaying: boolean;
  /** Open the film detail modal for the given movie id. */
  openFilmDetail: (movieId: number) => void;
  /** Close the film detail modal. */
  closeFilmDetail: () => void;
  /** Trigger the reveal animation. */
  startReveal: () => void;
  /** Mark the reveal animation as finished. */
  finishReveal: () => void;
  /** Reset to initial state. */
  reset: () => void;
}

export const useUiStore = create<UiStore>((set) => ({
  selectedMovieId: null,
  isFilmDetailOpen: false,
  isRevealPlaying: false,
  openFilmDetail: (movieId) =>
    set({ selectedMovieId: movieId, isFilmDetailOpen: true }),
  closeFilmDetail: () => set({ isFilmDetailOpen: false, selectedMovieId: null }),
  startReveal: () => set({ isRevealPlaying: true }),
  finishReveal: () => set({ isRevealPlaying: false }),
  reset: () =>
    set({ selectedMovieId: null, isFilmDetailOpen: false, isRevealPlaying: false }),
}));
