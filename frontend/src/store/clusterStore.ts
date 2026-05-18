import { create } from "zustand";

interface ClusterStore {
  /** ID of the currently selected cluster in the detail view. */
  selectedClusterId: string | null;
  /** Select a cluster by id. */
  selectCluster: (id: string | null) => void;
  /** Reset to initial state. */
  reset: () => void;
}

export const useClusterStore = create<ClusterStore>((set) => ({
  selectedClusterId: null,
  selectCluster: (id) => set({ selectedClusterId: id }),
  reset: () => set({ selectedClusterId: null }),
}));
