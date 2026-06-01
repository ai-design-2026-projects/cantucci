import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/dialog'
import { cn } from '@/lib/utils'
import { useEvalLabStore } from '../hooks/useEvalLabStore'
import { useSessionDetail } from '../hooks/useSessionDetail'
import { TurnIntentsTable } from './TurnIntentsTable'
import { JudgeScoreList } from './JudgeScoreList'
import { TranscriptLink } from './TranscriptLink'
import { PersonaDialog } from './PersonaDialog'

const STATUS_LABELS: Record<string, string> = {
    active: 'Active',
    finished_trajectory: 'Finished (trajectory)',
    finished_misbehaviour: 'Finished (misbehaviour)',
    finished_budget: 'Finished (budget)',
}

const STATUS_CHIP: Record<string, string> = {
    active: 'bg-yellow-400/20 text-yellow-600',
    finished_trajectory: 'bg-emerald-400/20 text-emerald-600',
    finished_misbehaviour: 'bg-red-400/20 text-red-600',
    finished_budget: 'bg-violet-400/20 text-violet-600',
}

/**
 * Centered dialog showing full detail for one eval session: session metadata
 * table, deterministic metrics, judge scores, turn intents, GT comparison,
 * and links to the conversation transcript and persona config.
 */
export function SessionSlideOver() {
    const { openSessionId, setOpenSessionId } = useEvalLabStore()
    const { data, isLoading } = useSessionDetail(openSessionId)

    return (
        <Dialog open={!!openSessionId} onOpenChange={(o) => !o && setOpenSessionId(null)}>
            <DialogContent className="max-w-[min(860px,95vw)] w-full h-[90vh] p-0 flex flex-col">
                <DialogHeader className="px-6 pt-5 pb-4 border-b border-[var(--color-border)] shrink-0">
                    <DialogTitle className="text-sm">Session Detail</DialogTitle>
                </DialogHeader>

                {isLoading && (
                    <div className="flex-1 flex items-center justify-center">
                        <div className="h-5 w-5 rounded-full border-2 border-[var(--color-primary)] border-t-transparent animate-spin" />
                    </div>
                )}

                {data && !isLoading && (
                    <div className="flex-1 overflow-y-auto scrollbar-styled flex flex-col gap-0">
                        <section className="px-6 py-4 border-b border-[var(--color-border)]">
                            <h3 className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-3">
                                Session info
                            </h3>
                            <table className="w-full text-xs border-collapse">
                                <tbody>
                                    {[
                                        { label: 'ID', value: data.id },
                                        {
                                            label: 'Status',
                                            value: (
                                                <span className={cn('text-[10px] px-1.5 py-0.5 rounded-full', STATUS_CHIP[data.status] ?? 'bg-[var(--color-border)] text-[var(--color-muted)]')}>
                                                    {STATUS_LABELS[data.status] ?? data.status}
                                                </span>
                                            ),
                                        },
                                        { label: 'Oracle rating', value: data.oracle_rating != null ? `${data.oracle_rating}/5` : '—' },
                                        { label: 'Condition', value: data.condition },
                                        { label: 'Ground truth', value: data.ground_truth?.slug ?? '—' },
                                        { label: 'GT intent', value: data.ground_truth?.intent_description ?? '—' },
                                        { label: 'Seed', value: String(data.seed) },
                                        { label: 'Persona', value: data.persona?.slug ?? '—' },
                                        { label: 'Verbosity', value: data.persona?.verbosity ?? '—' },
                                        { label: 'Patience', value: data.persona != null ? data.persona.patience.toFixed(2) : '—' },
                                        { label: 'Termination note', value: data.termination_rationale ?? '—' },
                                        { label: 'Created', value: new Date(data.created_at).toLocaleString() },
                                    ].map(({ label, value }) => (
                                        <tr key={label} className="border-b border-[var(--color-border)]">
                                            <td className="py-1.5 pr-4 text-[var(--color-muted)] font-medium w-1/3 text-[11px]">{label}</td>
                                            <td className="py-1.5 text-[var(--color-text)] text-[11px] font-mono break-all">{value}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </section>

                        {data.metrics && (
                            <section className="px-6 py-4 border-b border-[var(--color-border)]">
                                <h3 className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-3">
                                    Deterministic metrics
                                </h3>
                                <div className="grid grid-cols-3 gap-3">
                                    {[
                                        { label: 'Final clusters', value: String(data.metrics.final_num_clusters) },
                                        { label: 'Turns', value: String(data.metrics.num_turns) },
                                        { label: 'Operations', value: String(data.metrics.num_operations) },
                                        { label: 'Cost (USD)', value: `$${data.metrics.total_cost_usd.toFixed(5)}` },
                                        {
                                            label: 'Clarifier rate',
                                            value: data.metrics.clarifier_trigger_rate != null
                                                ? `${(data.metrics.clarifier_trigger_rate * 100).toFixed(1)}%`
                                                : '—',
                                        },
                                    ].map(({ label, value }) => (
                                        <div key={label} className="flex flex-col gap-0.5 p-2.5 rounded border border-[var(--color-border)] bg-[var(--color-surface)]">
                                            <span className="text-[9px] uppercase tracking-wide text-[var(--color-muted)]">{label}</span>
                                            <span className="text-sm font-bold text-[var(--color-text)] font-mono">{value}</span>
                                        </div>
                                    ))}
                                </div>
                            </section>
                        )}

                        <section className="px-6 py-4 border-b border-[var(--color-border)]">
                            <h3 className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-3">
                                Judge scores
                            </h3>
                            <JudgeScoreList scores={data.judge_scores} />
                        </section>

                        <section className="px-6 py-4 border-b border-[var(--color-border)]">
                            <h3 className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-3">
                                Turn intents
                            </h3>
                            {data.turn_intents.length > 0 ? (
                                <TurnIntentsTable intents={data.turn_intents} />
                            ) : (
                                <p className="text-xs text-[var(--color-muted)]">No turn intents recorded.</p>
                            )}
                        </section>

                        <section className="px-6 py-4 flex items-center gap-3 flex-wrap">
                            <TranscriptLink conversationId={data.conversation_id} />
                            <PersonaDialog session={data} />
                        </section>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    )
}
