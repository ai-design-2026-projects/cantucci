import { cn } from '@/lib/utils'
import type { RunDto } from '@/api/dto/eval'
import { colorForRun } from '../plots/colors'

const STATUS_COLORS: Record<string, string> = {
    running: 'bg-yellow-400/20 text-yellow-600',
    completed: 'bg-emerald-400/20 text-emerald-600',
    aborted: 'bg-red-400/20 text-red-600',
}

interface RunListItemProps {
    run: RunDto
    isSelected: boolean
    isCompared: boolean
    compareMode: boolean
    onSelect: () => void
    onToggleCompare: () => void
}

/**
 * Single row in the run list. Shows run name, condition badge, model, status,
 * and a color swatch. In compare mode a checkbox appears for multi-selection.
 */
export function RunListItem({
    run,
    isSelected,
    isCompared,
    compareMode,
    onSelect,
    onToggleCompare,
}: RunListItemProps) {
    const started = new Date(run.started_at).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
    })

    return (
        <div
            className={cn(
                'flex items-start gap-2 px-3 py-2.5 cursor-pointer hover:bg-[var(--color-elevated)] transition-colors border-b border-[var(--color-border)]',
                isSelected && 'bg-[var(--color-elevated)]',
            )}
            onClick={compareMode ? onToggleCompare : onSelect}
        >
            {compareMode && (
                <input
                    type="checkbox"
                    checked={isCompared}
                    onChange={onToggleCompare}
                    onClick={(e) => e.stopPropagation()}
                    className="mt-0.5 shrink-0 accent-[var(--color-primary)]"
                />
            )}

            <div
                className="mt-1 h-2 w-2 rounded-full shrink-0"
                style={{ background: colorForRun(run.id) }}
            />

            <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                <span className="text-xs font-medium text-[var(--color-text)] truncate">
                    {run.name ?? run.id.slice(0, 8)}
                </span>

                <div className="flex items-center gap-1 flex-wrap">
                    {run.condition && (
                        <span className="text-[10px] px-1.5 py-0 rounded-full bg-[var(--color-border)] text-[var(--color-muted)]">
                            {run.condition}
                        </span>
                    )}
                    {run.model_version && (
                        <span className="text-[10px] px-1.5 py-0 rounded-full bg-[var(--color-border)] text-[var(--color-muted)]">
                            {run.model_version}
                        </span>
                    )}
                    <span className={cn('text-[10px] px-1.5 py-0 rounded-full', STATUS_COLORS[run.status] ?? 'bg-[var(--color-border)] text-[var(--color-muted)]')}>
                        {run.status}
                    </span>
                </div>

                <span className="text-[10px] text-[var(--color-muted)]">{started}</span>
            </div>
        </div>
    )
}
