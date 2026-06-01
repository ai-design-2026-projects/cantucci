import type { GroundTruthDto, TurnIntentDto } from '@/api/dto/eval'
import { cn } from '@/lib/utils'

interface GTComparisonTableProps {
    groundTruth: GroundTruthDto
    intents: TurnIntentDto[]
}

const NAVIGATION_OPS = new Set(['cluster', 'merge', 'focus', 'cross_filter', 'exclude'])

/**
 * Aligned two-column table comparing the ground-truth trajectory against
 * executed turns. GT ops are on the left; the best matching executed op is
 * on the right. Recall summary shown below.
 */
export function GTComparisonTable({ groundTruth, intents }: GTComparisonTableProps) {
    const gtOps = groundTruth.operations.filter((op) => NAVIGATION_OPS.has(op.op))
    const executedOps = intents.filter((t) => NAVIGATION_OPS.has(t.mode))

    const normalize = (s: string | null | undefined) => (s ?? '').trim().toLowerCase()

    const executedSet = new Set(
        executedOps.map((t) => `${t.mode}||${normalize(t.concept)}`)
    )

    const matchedGt = new Set<string>()
    const rows: Array<{
        gt: { op: string; concept: string } | null
        executed: { mode: string; concept: string | null; turn: number } | null
        matched: boolean
    }> = []

    for (const op of gtOps) {
        const key = `${op.op}||${normalize(op.concept)}`
        const matched = executedSet.has(key)
        if (matched) matchedGt.add(key)

        const executedMatch = matched
            ? executedOps.find(
                  (t) => t.mode === op.op && normalize(t.concept) === normalize(op.concept)
              ) ?? null
            : null

        rows.push({
            gt: { op: op.op, concept: op.concept },
            executed: executedMatch
                ? { mode: executedMatch.mode, concept: executedMatch.concept, turn: executedMatch.turn_number }
                : null,
            matched,
        })
    }

    const extraExec = executedOps.filter(
        (t) => !matchedGt.has(`${t.mode}||${normalize(t.concept)}`)
    )
    for (const t of extraExec) {
        rows.push({ gt: null, executed: { mode: t.mode, concept: t.concept, turn: t.turn_number }, matched: false })
    }

    const recall = gtOps.length > 0 ? matchedGt.size / gtOps.length : null

    return (
        <div className="flex flex-col gap-3">
            <div className="overflow-x-auto">
                <table className="w-full text-[11px] border-collapse">
                    <thead>
                        <tr className="border-b border-[var(--color-border)]">
                            <th className="text-left py-1.5 px-2 text-[var(--color-muted)] font-medium w-1/2">GT Target</th>
                            <th className="text-left py-1.5 px-2 text-[var(--color-muted)] font-medium w-1/2">Executed</th>
                            <th className="text-center py-1.5 px-2 text-[var(--color-muted)] font-medium w-6"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((row, i) => (
                            <tr
                                key={i}
                                className={cn(
                                    'border-b border-[var(--color-border)]',
                                    row.matched && 'bg-emerald-500/5',
                                    !row.matched && row.gt && 'bg-red-500/5',
                                    !row.gt && 'bg-amber-500/5',
                                )}
                            >
                                <td className="py-1 px-2">
                                    {row.gt ? (
                                        <span>
                                            <span className="font-mono text-[10px] text-[var(--color-muted)]">{row.gt.op}</span>
                                            {row.gt.concept && (
                                                <span className="ml-1 text-[var(--color-text)]">{row.gt.concept}</span>
                                            )}
                                        </span>
                                    ) : (
                                        <span className="text-[var(--color-muted)] italic">—</span>
                                    )}
                                </td>
                                <td className="py-1 px-2">
                                    {row.executed ? (
                                        <span>
                                            <span className="font-mono text-[10px] text-[var(--color-muted)]">
                                                t{row.executed.turn} {row.executed.mode}
                                            </span>
                                            {row.executed.concept && (
                                                <span className="ml-1 text-[var(--color-text)]">{row.executed.concept}</span>
                                            )}
                                        </span>
                                    ) : (
                                        <span className="text-[var(--color-muted)] italic">not executed</span>
                                    )}
                                </td>
                                <td className="py-1 px-2 text-center text-sm">
                                    {row.gt && row.matched && <span className="text-emerald-600">✓</span>}
                                    {row.gt && !row.matched && <span className="text-red-500">✗</span>}
                                    {!row.gt && <span className="text-amber-500" title="Extra op not in GT">+</span>}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <div className="flex items-center gap-2 text-[11px]">
                <span className="text-[var(--color-muted)]">Operation recall:</span>
                <span className="font-semibold text-[var(--color-text)]">
                    {recall != null ? `${matchedGt.size}/${gtOps.length} (${(recall * 100).toFixed(0)}%)` : 'N/A'}
                </span>
                <span className="text-[10px] text-[var(--color-muted)] ml-2">
                    <span className="text-emerald-600">✓ matched</span>
                    <span className="mx-1">/</span>
                    <span className="text-red-500">✗ missed</span>
                    <span className="mx-1">/</span>
                    <span className="text-amber-500">+ extra</span>
                </span>
            </div>
        </div>
    )
}
