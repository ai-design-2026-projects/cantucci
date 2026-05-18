import { create } from "zustand";
import type { ProgressStep } from "@/features/conversation/services/turnService";

interface UiStore {
  /** TMDB movie id of the film currently open in the detail modal. */
  selectedMovieId: number | null;
  /** Whether the film detail modal is open. */
  isFilmDetailOpen: boolean;
  /**
   * The pipeline step the backend is currently executing for the in-flight
   * turn, or ``null`` when no turn is running. Driven by NDJSON progress
   * events streamed from POST /sessions/{id}/turns.
   */
  currentStep: ProgressStep | null;
  /**
   * True after the user clicks "Review conversation" in the StopOverlay,
   * dismissing it. Enables the "Go back to recommendations" button in chat.
   * Reset when the session changes.
   */
  stopOverlayDismissed: boolean;
  /** Whether the session history sidebar is currently visible. */
  sidebarOpen: boolean;
  /** Open the film detail modal for the given movie id. */
  openFilmDetail: (movieId: number) => void;
  /** Close the film detail modal. */
  closeFilmDetail: () => void;
  /** Set the active pipeline step (called on progress events). */
  setCurrentStep: (step: ProgressStep | null) => void;
  /** Mark the stop overlay as dismissed (user clicked "Review conversation"). */
  dismissStopOverlay: () => void;
  /** Re-open the stop overlay (user clicked "Go back to recommendations"). */
  reopenStopOverlay: () => void;
  /** Toggle the sidebar open/closed. */
  toggleSidebar: () => void;
  /** Reset to initial state. */
  reset: () => void;
}

export const useUiStore = create<UiStore>((set) => ({
  selectedMovieId: null,
  isFilmDetailOpen: false,
  currentStep: null,
  stopOverlayDismissed: false,
  sidebarOpen: true,
  openFilmDetail: (movieId) =>
    set({ selectedMovieId: movieId, isFilmDetailOpen: true }),
  closeFilmDetail: () => set({ isFilmDetailOpen: false, selectedMovieId: null }),
  setCurrentStep: (step) => set({ currentStep: step }),
  dismissStopOverlay: () => set({ stopOverlayDismissed: true }),
  reopenStopOverlay: () => set({ stopOverlayDismissed: false }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  reset: () =>
    set({
      selectedMovieId: null,
      isFilmDetailOpen: false,
      currentStep: null,
      stopOverlayDismissed: false,
    }),
}));
