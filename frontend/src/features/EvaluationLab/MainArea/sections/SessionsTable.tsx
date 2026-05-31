import { useState } from 'react'
import { ChevronUp, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { RunAggregateDto, SessionAggregateRowDto } from '@/api/dto/eval'
import { colorForRun } from '../../plots/colors'
import { fmt } from '../../plots/stats'
import { useEvalLabStore } from '../../hooks/useEvalLabStore'

type SortKey = 'status' | 'num_turns' | 'cost' | 'oracle_rating' | 'mean_judge'

interface TableRow {
    session: SessionAggregateRowDto
    runId: string
    runName: string
    meanJudge: number | null
}

function sortRows(rows: TableRow[], key: SortKey, dir: 'asc' | 'desc'): TableRow[] {
    return [...rows].sort((a, b) => {
        let va: number | string | null = null
        let vb: number | string | null = null
        switch (key) {
            case 'status': va = a.session.status; vb = b.session.status; break
            case 'num_turns': va = a.session.metrics?.num_turns ?? null; vb = b.session.metrics?.num_turns ?? null; break
            case 'cost': va = a.session.metrics?.total_cost_usd ?? null; vb = b.session.metrics?.total_cost_usd ?? null; break
            case 'oracle_rating': va = a.session.oracle_rating ?? null; vb = b.session.oracle_rating ?? null; break
            case 'mean_judge': va = a.meanJudge; vb = b.meanJudge; break
        }
        if (va == null && vb == null) return 0
        if (va == null) return 1
        if (vb == null) return -1
        const cmp = typeof va === 'string' ? va.localeCompare(vb as string) : (va as number) - (vb as number)
        return dir === 'asc' ? cmp : -cmp
    })
}

interface SortHeaderProps {
    label: string
    sortKey: SortKey
    current: SortKey
    dir: 'asc' | 'desc'
    onSort: (k: SortKey) => void
}

function SortHeader({ label, sortKey, current, dir, onSort }: SortHeaderProps) {
    return (
        <th
            className="text-left py-2 px-3 text-[var(--color-muted)] font-medium text-[11px] cursor-pointer hover:text-[var(--color-text)] select-none"
            onClick={() => onSort(sortKey)}
        >
            <div className="flex items-center gap-1">
                {label}
                {current === sortKey ? (
                    dir === 'asc' ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />
                ) : (
                    <ChevronDown className="h-3 w-3 opacity-30" />
                )}
            </div>
        </th>
    )
}

interface SessionsTableProps {
    aggregates: RunAggregateDto[]
}

/**
 * Sortable sessions table. In compare mode a "run" column is added.
 * Row click opens the session slide-over.
 */
export function SessionsTable({ aggregates }: SessionsTableProps) {
    const { setOpenSessionId, compareMode } = useEvalLabStore()
    const [sortKey, setSortKey] = useState<SortKey>('num_turns')
    const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

    const handleSort = (key: SortKey) => {
        if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
        else { setSortKey(key); setSortDir('desc') }
    }

    const rows: TableRow[] = aggregates.flatMap((agg) =>
        agg.sessions.map((s) => {
            const scores = s.judge_scores.map((j) => j.score)
            const meanJudge = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : null
            return {
                session: s,
                runId: agg.run.id,
                runName: agg.run.name ?? agg.run.id.slice(0, 8),
                meanJudge,
            }
        })
    )

    const sorted = sortRows(rows, sortKey, sortDir)

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
                <thead>
                    <tr className="border-b border-[var(--color-border)]">
                        {compareMode && (
                            <th className="text-left py-2 px-3 text-[var(--color-muted)] font-medium text-[11px]">Run</th>
                        )}
                        <th className="text-left py-2 px-3 text-[var(--color-muted)] font-medium text-[11px]">Session</th>
                        <SortHeader label="Status" sortKey="status" current={sortKey} dir={sortDir} onSort={handleSort} />
                        <SortHeader label="Turns" sortKey="num_turns" current={sortKey} dir={sortDir} onSort={handleSort} />
                        <SortHeader label="Cost" sortKey="cost" current={sortKey} dir={sortDir} onSort={handleSort} />
                        <SortHeader label="Oracle" sortKey="oracle_rating" current={sortKey} dir={sortDir} onSort={handleSort} />
                        <SortHeader label="Judge avg" sortKey="mean_judge" current={sortKey} dir={sortDir} onSort={handleSort} />
                    </tr>
                </thead>
                <tbody>
                    {sorted.map(({ session, runId, runName, meanJudge }) => (
                        <tr
                            key={session.eval_session_id}
                            className="border-b border-[var(--color-border)] hover:bg-[var(--color-elevated)] cursor-pointer"
                            onClick={() => setOpenSessionId(session.eval_session_id)}
                        >
                            {compareMode && (
                                <td className="py-1.5 px-3">
                                    <div className="flex items-center gap-1.5">
                                        <div className="h-2 w-2 rounded-full shrink-0" style={{ background: colorForRun(runId) }} />
                                        <span className="truncate max-w-[80px]">{runName}</span>
                                    </div>
                                </td>
                            )}
                            <td className="py-1.5 px-3 font-mono text-[10px] text-[var(--color-muted)]">
                                {session.eval_session_id.slice(0, 8)}
                            </td>
                            <td className="py-1.5 px-3">
                                <span className={cn(
                                    'text-[10px] px-1.5 py-0 rounded-full',
                                    session.status === 'finished_trajectory' ? 'bg-emerald-400/20 text-emerald-600' :
                                    session.status === 'finished_misbehaviour' ? 'bg-red-400/20 text-red-600' :
                                    session.status === 'finished_budget' ? 'bg-violet-400/20 text-violet-600' :
                                    'bg-[var(--color-border)] text-[var(--color-muted)]'
                                )}>
                                    {session.status}
                                </span>
                            </td>
                            <td className="py-1.5 px-3 font-mono">{session.metrics?.num_turns ?? '—'}</td>
                            <td className="py-1.5 px-3 font-mono">{session.metrics ? fmt(session.metrics.total_cost_usd) : '—'}</td>
                            <td className="py-1.5 px-3 font-mono">{session.oracle_rating ?? '—'}</td>
                            <td className="py-1.5 px-3 font-mono">{meanJudge != null ? fmt(meanJudge) : '—'}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
            {sorted.length === 0 && (
                <p className="text-xs text-[var(--color-muted)] px-3 py-4">No sessions.</p>
            )}
        </div>
    )
}
