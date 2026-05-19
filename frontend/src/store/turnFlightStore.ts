import { create } from "zustand";
import type { ProgressStep } from "@/features/conversation/services/turnService";

interface FlightEntry {
  isPending: boolean;
  lastStep: ProgressStep | null;
}

interface TurnFlightStore {
  /** Per-session in-flight state, keyed by session UUID. */
  flights: Map<string, FlightEntry>;
  /** Mark a turn as started for the given session. */
  markStarted: (sessionId: string) => void;
  /** Update the latest progress step for a session's in-flight turn. */
  markStep: (sessionId: string, step: ProgressStep) => void;
  /** Mark a session's turn as finished (clears pending flag). */
  markFinished: (sessionId: string) => void;
}

export const useTurnFlightStore = create<TurnFlightStore>((set) => ({
  flights: new Map(),

  markStarted: (sessionId) =>
    set((s) => {
      const next = new Map(s.flights);
      next.set(sessionId, { isPending: true, lastStep: null });
      return { flights: next };
    }),

  markStep: (sessionId, step) =>
    set((s) => {
      const next = new Map(s.flights);
      const entry = next.get(sessionId);
      if (entry?.isPending) {
        next.set(sessionId, { ...entry, lastStep: step });
      }
      return { flights: next };
    }),

  markFinished: (sessionId) =>
    set((s) => {
      const next = new Map(s.flights);
      next.set(sessionId, { isPending: false, lastStep: null });
      return { flights: next };
    }),
}));

const IDLE_ENTRY: FlightEntry = { isPending: false, lastStep: null };

/** Convenience selector: returns the flight entry for a session or a stable idle entry. */
export function useSessionFlight(sessionId: string | null): FlightEntry {
  return useTurnFlightStore((s) =>
    (sessionId && s.flights.get(sessionId)) || IDLE_ENTRY
  );
}
