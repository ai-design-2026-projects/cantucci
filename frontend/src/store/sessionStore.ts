import { create } from "zustand";

export type OracleType = "human" | "llm";

interface SessionStore {
  /** Active session UUID, or null before the first session is created. */
  sessionId: string | null;
  /** Current turn index for display purposes. */
  turnCursor: number;
  /** Oracle type — "human" for interactive use; "llm" for evaluation harness. */
  oracleType: OracleType;
  /** Set the active session id. */
  setSessionId: (id: string) => void;
  /** Advance the turn cursor. */
  incrementTurn: () => void;
  /** Reset store to initial state (called on session restart). */
  reset: () => void;
}

export const useSessionStore = create<SessionStore>((set) => ({
  sessionId: null,
  turnCursor: 0,
  oracleType: "human",
  setSessionId: (id) => set({ sessionId: id }),
  incrementTurn: () => set((s) => ({ turnCursor: s.turnCursor + 1 })),
  reset: () => set({ sessionId: null, turnCursor: 0 }),
}));
