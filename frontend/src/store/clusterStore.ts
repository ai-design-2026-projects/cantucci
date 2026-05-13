import { create } from "zustand";
import type { ConvergedClusterPublic } from "@/utils/types";

interface ClusterStore {
  /** Cached converged cluster payload, set after the reveal loads. */
  convergedCluster: ConvergedClusterPublic | null;
  /** ID of the currently selected cluster in the post-reveal view. */
  selectedClusterId: string | null;
  /** Set the cached converged cluster. */
  setConvergedCluster: (c: ConvergedClusterPublic) => void;
  /** Select a cluster by id. */
  selectCluster: (id: string) => void;
  /** Reset to initial state. */
  reset: () => void;
}

export const useClusterStore = create<ClusterStore>((set) => ({
  convergedCluster: null,
  selectedClusterId: null,
  setConvergedCluster: (c) => set({ convergedCluster: c }),
  selectCluster: (id) => set({ selectedClusterId: id }),
  reset: () => set({ convergedCluster: null, selectedClusterId: null }),
}));
