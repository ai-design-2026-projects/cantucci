import { create } from "zustand";
import type { User } from "@/utils/types";

type AuthStatus = "idle" | "loading" | "authenticated" | "anonymous";

interface AuthStore {
  /** Currently authenticated user, or null if anonymous / not yet resolved. */
  user: User | null;
  /** Lifecycle status of the auth bootstrap. */
  status: AuthStatus;
  setUser: (user: User | null) => void;
  setStatus: (status: AuthStatus) => void;
  /** Reset to initial state — call on logout or 401. */
  reset: () => void;
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  status: "idle",
  setUser: (user) => set({ user }),
  setStatus: (status) => set({ status }),
  reset: () => set({ user: null, status: "anonymous" }),
}));
