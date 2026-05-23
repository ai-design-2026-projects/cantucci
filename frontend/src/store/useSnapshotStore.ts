import { create } from 'zustand'

interface SnapshotState {
	activeSnapshotId: string | null
	selectedClusterId: string | null
	setActiveSnapshotId: (id: string | null) => void
	setSelectedClusterId: (id: string | null) => void
}

/**
 * Manages the active cluster snapshot and selected cluster within it.
 * Active snapshot drives what the scatter plot and cluster list display.
 */
export const useSnapshotStore = create<SnapshotState>((set) => ({
	activeSnapshotId: null,
	selectedClusterId: null,
	setActiveSnapshotId: (id) => set({ activeSnapshotId: id, selectedClusterId: null }),
	setSelectedClusterId: (id) => set({ selectedClusterId: id }),
}))
