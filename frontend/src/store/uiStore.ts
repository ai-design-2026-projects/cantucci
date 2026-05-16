import { create } from "zustand";
import type { ProgressStep } from "@/features/conversation/services/turnService";

interface UiStore {
  /** TMDB movie id of the film currently open in the detail modal. */
  selectedMovieId: number | null;
  /** Whether the film detail modal is open. */
  isFilmDetailOpen: boolean;
  /** Whether the one-shot cinematic reveal animation is playing. */
  isRevealPlaying: boolean;
  /**
   * The pipeline step the backend is currently executing for the in-flight
   * turn, or ``null`` when no turn is running. Driven by NDJSON progress
   * events streamed from POST /sessions/{id}/turns.
   */
  currentStep: ProgressStep | null;
  /** Open the film detail modal for the given movie id. */
  openFilmDetail: (movieId: number) => void;
  /** Close the film detail modal. */
  closeFilmDetail: () => void;
  /** Trigger the reveal animation. */
  startReveal: () => void;
  /** Mark the reveal animation as finished. */
  finishReveal: () => void;
  /** Set the active pipeline step (called on progress events). */
  setCurrentStep: (step: ProgressStep | null) => void;
  /** Reset to initial state. */
  reset: () => void;
}

export const useUiStore = create<UiStore>((set) => ({
  selectedMovieId: null,
  isFilmDetailOpen: false,
  isRevealPlaying: false,
  currentStep: null,
  openFilmDetail: (movieId) =>
    set({ selectedMovieId: movieId, isFilmDetailOpen: true }),
  closeFilmDetail: () => set({ isFilmDetailOpen: false, selectedMovieId: null }),
  startReveal: () => set({ isRevealPlaying: true }),
  finishReveal: () => set({ isRevealPlaying: false }),
  setCurrentStep: (step) => set({ currentStep: step }),
  reset: () =>
    set({
      selectedMovieId: null,
      isFilmDetailOpen: false,
      isRevealPlaying: false,
      currentStep: null,
    }),
}));
