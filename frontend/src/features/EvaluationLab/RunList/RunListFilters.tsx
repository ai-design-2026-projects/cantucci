import { Search } from 'lucide-react'
import { useEvalLabStore } from '../hooks/useEvalLabStore'

const CONDITIONS = ['conversational', 'monolithic', 'human']
const STATUSES = ['running', 'completed', 'aborted']

/**
 * Filter and sort controls for the run list.
 */
export function RunListFilters() {
    const { filters, sort, setFilters, setSort } = useEvalLabStore()

    return (
        <div className="flex flex-col gap-1.5 px-2 py-2 border-b border-[var(--color-border)]">
            <div className="relative">
                <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--color-muted)]" />
                <input
                    className="w-full pl-6 pr-2 py-1 text-xs bg-[var(--color-bg)] border border-[var(--color-border)] rounded text-[var(--color-text)] placeholder:text-[var(--color-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
                    placeholder="Search runs…"
                    value={filters.search}
                    onChange={(e) => setFilters({ search: e.target.value })}
                />
            </div>

            <select
                className="w-full py-1 px-1.5 text-xs bg-[var(--color-bg)] border border-[var(--color-border)] rounded text-[var(--color-text)] focus:outline-none"
                value={filters.condition}
                onChange={(e) => setFilters({ condition: e.target.value })}
            >
                <option value="">All conditions</option>
                {CONDITIONS.map((c) => (
                    <option key={c} value={c}>{c}</option>
                ))}
            </select>

            <select
                className="w-full py-1 px-1.5 text-xs bg-[var(--color-bg)] border border-[var(--color-border)] rounded text-[var(--color-text)] focus:outline-none"
                value={filters.status}
                onChange={(e) => setFilters({ status: e.target.value })}
            >
                <option value="">All statuses</option>
                {STATUSES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                ))}
            </select>

            <select
                className="w-full py-1 px-1.5 text-xs bg-[var(--color-bg)] border border-[var(--color-border)] rounded text-[var(--color-text)] focus:outline-none"
                value={`${sort.key}:${sort.dir}`}
                onChange={(e) => {
                    const [key, dir] = e.target.value.split(':') as [typeof sort.key, 'asc' | 'desc']
                    setSort({ key, dir })
                }}
            >
                <option value="started_at:desc">Newest first</option>
                <option value="started_at:asc">Oldest first</option>
            </select>
        </div>
    )
}
