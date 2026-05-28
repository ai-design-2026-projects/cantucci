import { create } from 'zustand'

interface EvalLabFilters {
    condition: string
    model_version: string
    status: string
    search: string
}

interface EvalLabSort {
    key: 'started_at' | 'n_sessions' | 'mean_cost' | 'mean_oracle_rating'
    dir: 'asc' | 'desc'
}

interface EvalLabState {
    selectedRunId: string | null
    compareRunIds: string[]
    compareMode: boolean
    configPanelOpen: boolean
    openSessionId: string | null
    filters: EvalLabFilters
    sort: EvalLabSort

    setSelectedRunId: (id: string | null) => void
    toggleCompareRun: (id: string) => void
    setCompareMode: (on: boolean) => void
    setConfigPanelOpen: (open: boolean) => void
    setOpenSessionId: (id: string | null) => void
    setFilters: (filters: Partial<EvalLabFilters>) => void
    setSort: (sort: EvalLabSort) => void
}

/**
 * Client-only state for the Eval Lab page. React Query owns server state; this
 * store owns UI state: selection, compare mode, panel visibility, and filters.
 */
export const useEvalLabStore = create<EvalLabState>((set) => ({
    selectedRunId: null,
    compareRunIds: [],
    compareMode: false,
    configPanelOpen: true,
    openSessionId: null,
    filters: { condition: '', model_version: '', status: '', search: '' },
    sort: { key: 'started_at', dir: 'desc' },

    setSelectedRunId: (id) =>
        set((s) => ({
            selectedRunId: id,
            compareRunIds: s.compareMode && id ? [id, ...s.compareRunIds.filter((r) => r !== id)] : s.compareRunIds,
        })),

    toggleCompareRun: (id) =>
        set((s) => ({
            compareRunIds: s.compareRunIds.includes(id)
                ? s.compareRunIds.filter((r) => r !== id)
                : [...s.compareRunIds, id],
        })),

    setCompareMode: (on) =>
        set((s) => ({
            compareMode: on,
            compareRunIds: on && s.selectedRunId ? [s.selectedRunId] : [],
        })),

    setConfigPanelOpen: (open) => set({ configPanelOpen: open }),
    setOpenSessionId: (id) => set({ openSessionId: id }),
    setFilters: (filters) => set((s) => ({ filters: { ...s.filters, ...filters } })),
    setSort: (sort) => set({ sort }),
}))
