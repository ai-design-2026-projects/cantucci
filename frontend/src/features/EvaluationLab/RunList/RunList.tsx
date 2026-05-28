import { useState } from 'react'
import { PanelLeftClose, PanelLeftOpen, GitCompareArrows } from 'lucide-react'
import { Button } from '@/components/button'
import { cn } from '@/lib/utils'
import type { RunDto } from '@/api/dto/eval'
import { useRuns } from '../hooks/useRuns'
import { useEvalLabStore } from '../hooks/useEvalLabStore'
import { RunListItem } from './RunListItem'
import { RunListFilters } from './RunListFilters'

/**
 * Collapsible left panel showing all eval runs. Mirrors the HistorySidebar pattern.
 * In compare mode each item gets a checkbox; compare button toggles the mode.
 */
export function RunList() {
    const { data: runs, isLoading } = useRuns()
    const {
        selectedRunId,
        compareRunIds,
        compareMode,
        filters,
        sort,
        setSelectedRunId,
        toggleCompareRun,
        setCompareMode,
    } = useEvalLabStore()

    const [open, setOpen] = useState(true)

    const filtered = (runs ?? [])
        .filter((r) => {
            if (filters.condition && r.condition !== filters.condition) return false
            if (filters.status && r.status !== filters.status) return false
            if (filters.model_version && r.model_version !== filters.model_version) return false
            if (filters.search) {
                const q = filters.search.toLowerCase()
                if (!r.name?.toLowerCase().includes(q) && !r.id.includes(q)) return false
            }
            return true
        })
        .sort((a: RunDto, b: RunDto) => {
            const mul = sort.dir === 'asc' ? 1 : -1
            if (sort.key === 'started_at') {
                return mul * (new Date(a.started_at).getTime() - new Date(b.started_at).getTime())
            }
            return 0
        })

    return (
        <div className={cn(
            'flex-shrink-0 flex flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] transition-all duration-200 overflow-hidden',
            open ? 'w-72' : 'w-14',
        )}>
            <div className={cn(
                'flex items-center border-b border-[var(--color-border)] h-12 flex-shrink-0',
                open ? 'justify-between px-3' : 'justify-center',
            )}>
                {open && (
                    <div className="flex items-center gap-1">
                        <span className="text-sm font-medium text-[var(--color-text)]">Runs</span>
                        {compareMode && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-[var(--color-primary)]/20 text-[var(--color-primary)]">
                                compare
                            </span>
                        )}
                    </div>
                )}
                <div className="flex items-center gap-0.5">
                    {open && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            title={compareMode ? 'Exit compare' : 'Compare runs'}
                            onClick={() => setCompareMode(!compareMode)}
                        >
                            <GitCompareArrows className="h-3.5 w-3.5" />
                        </Button>
                    )}
                    <Button variant="ghost" size="icon" onClick={() => setOpen((o) => !o)} className="h-8 w-8">
                        {open ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
                    </Button>
                </div>
            </div>

            {open && (
                <>
                    <RunListFilters />
                    <div className="flex-1 overflow-y-auto">
                        {isLoading && (
                            <p className="text-xs text-[var(--color-muted)] px-4 py-3">Loading…</p>
                        )}
                        {!isLoading && filtered.length === 0 && (
                            <p className="text-xs text-[var(--color-muted)] px-4 py-3">No runs found</p>
                        )}
                        {filtered.map((run) => (
                            <RunListItem
                                key={run.id}
                                run={run}
                                isSelected={selectedRunId === run.id}
                                isCompared={compareRunIds.includes(run.id)}
                                compareMode={compareMode}
                                onSelect={() => setSelectedRunId(run.id)}
                                onToggleCompare={() => toggleCompareRun(run.id)}
                            />
                        ))}
                    </div>
                </>
            )}
        </div>
    )
}
