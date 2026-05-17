import { create } from "zustand";
import type { ClusterSnapshotPayload } from "@/utils/types";

interface ClusterSnapshotStore {
  /** Current live cluster list, updated mid-turn via NDJSON stream. */
  clusters: ClusterSnapshotPayload[];
  /** True while a turn is in-flight and the snapshot may still update. */
  isRefining: boolean;
  /** Replace the snapshot with fresh data from a stream event. */
  setSnapshot: (clusters: ClusterSnapshotPayload[]) => void;
  /** Toggle the refining state (true = in-flight, false = settled). */
  setRefining: (refining: boolean) => void;
  /** Reset to initial state. */
  reset: () => void;
}

export const useClusterSnapshotStore = create<ClusterSnapshotStore>((set) => ({
  clusters: [],
  isRefining: false,
  setSnapshot: (clusters) => set({ clusters, isRefining: true }),
  setRefining: (refining) => set({ isRefining: refining }),
  reset: () => set({ clusters: [], isRefining: false }),
}));
