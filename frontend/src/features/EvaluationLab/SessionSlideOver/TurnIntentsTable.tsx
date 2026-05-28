import { cn } from '@/lib/utils'
import type { TurnIntentDto } from '@/api/dto/eval'

interface TurnIntentsTableProps {
    intents: TurnIntentDto[]
}

/**
 * Scrollable table showing per-turn intent data: turn number, mode, concept,
 * confidence, and whether the clarifier fired.
 */
export function TurnIntentsTable({ intents }: TurnIntentsTableProps) {
    return (
        <div className="overflow-x-auto">
            <table className="w-full text-[11px] border-collapse">
                <thead>
                    <tr className="border-b border-[var(--color-border)]">
                        {['Turn', 'Mode', 'Concept', 'Conf', 'Clarifier'].map((h) => (
                            <th key={h} className="text-left py-1.5 px-2 text-[var(--color-muted)] font-medium">
                                {h}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {intents.map((t) => (
                        <tr
                            key={t.id}
                            className={cn(
                                'border-b border-[var(--color-border)] hover:bg-[var(--color-elevated)]',
                                t.clarifier_fired && 'bg-red-500/5',
                            )}
                        >
                            <td className="py-1 px-2 font-mono">{t.turn_number}</td>
                            <td className="py-1 px-2">
                                <span className="px-1.5 py-0 rounded-full text-[10px] bg-[var(--color-border)] text-[var(--color-muted)]">
                                    {t.mode}
                                </span>
                            </td>
                            <td className="py-1 px-2 text-[var(--color-text)] max-w-[120px] truncate" title={t.concept ?? ''}>
                                {t.concept ?? '—'}
                            </td>
                            <td className="py-1 px-2 font-mono">{t.confidence.toFixed(3)}</td>
                            <td className="py-1 px-2 text-center">
                                {t.clarifier_fired ? (
                                    <span className="text-red-500 font-bold">▲</span>
                                ) : (
                                    <span className="text-[var(--color-muted)]">—</span>
                                )}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}
