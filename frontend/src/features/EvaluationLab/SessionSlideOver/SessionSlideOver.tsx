import {
    Sheet,
    SheetContent,
    SheetHeader,
    SheetTitle,
} from '@/components/sheet'
import { useEvalLabStore } from '../hooks/useEvalLabStore'
import { useSessionDetail } from '../hooks/useSessionDetail'
import { PerTurnConfidenceChart } from './PerTurnConfidenceChart'
import { TurnIntentsTable } from './TurnIntentsTable'
import { JudgeScoreList } from './JudgeScoreList'
import { TranscriptLink } from './TranscriptLink'
import { colorForRun } from '../plots/colors'

/**
 * Right-side slide-over showing full detail for one eval session:
 * per-turn confidence chart, judge score rationales, turn-intents table,
 * and a link to the conversation transcript.
 */
export function SessionSlideOver() {
    const { openSessionId, setOpenSessionId, selectedRunId } = useEvalLabStore()
    const { data, isLoading } = useSessionDetail(openSessionId)
    const color = selectedRunId ? colorForRun(selectedRunId) : '#6366f1'

    return (
        <Sheet open={!!openSessionId} onOpenChange={(o) => !o && setOpenSessionId(null)}>
            <SheetContent side="right" className="w-[480px] max-w-full overflow-y-auto flex flex-col gap-0 p-0">
                <SheetHeader className="px-6 pt-6 pb-4 border-b border-[var(--color-border)]">
                    <SheetTitle className="text-base">Session Detail</SheetTitle>
                    {data && (
                        <div className="flex flex-wrap gap-1.5 mt-1">
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--color-border)] text-[var(--color-muted)] font-mono">
                                {data.id.slice(0, 8)}
                            </span>
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--color-border)] text-[var(--color-muted)]">
                                {data.status}
                            </span>
                            {data.oracle_rating != null && (
                                <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-400/20 text-amber-600">
                                    oracle {data.oracle_rating}/5
                                </span>
                            )}
                            {data.persona && (
                                <span className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--color-border)] text-[var(--color-muted)] font-mono">
                                    {data.persona.slug}
                                </span>
                            )}
                            {data.persona && (
                                <span className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--color-border)] text-[var(--color-muted)]">
                                    {data.persona.verbosity}
                                </span>
                            )}
                            {data.persona && (
                                <span className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--color-border)] text-[var(--color-muted)]">
                                    patience {data.persona.patience}
                                </span>
                            )}
                        </div>
                    )}
                    {data?.termination_rationale && (
                        <p className="text-[11px] text-[var(--color-muted)] mt-1 leading-relaxed">
                            {data.termination_rationale}
                        </p>
                    )}
                </SheetHeader>

                {isLoading && (
                    <div className="flex-1 flex items-center justify-center">
                        <div className="h-5 w-5 rounded-full border-2 border-[var(--color-primary)] border-t-transparent animate-spin" />
                    </div>
                )}

                {data && !isLoading && (
                    <div className="flex flex-col gap-0 flex-1">
                        <section className="px-6 py-4 border-b border-[var(--color-border)]">
                            <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-3">
                                Confidence over turns
                                <span className="normal-case font-normal ml-1">(▲ = clarifier fired, dashed = 95% CI mean)</span>
                            </h3>
                            {data.turn_intents.length > 0 ? (
                                <PerTurnConfidenceChart intents={data.turn_intents} color={color} />
                            ) : (
                                <p className="text-xs text-[var(--color-muted)]">No turn intents recorded.</p>
                            )}
                        </section>

                        <section className="px-6 py-4 border-b border-[var(--color-border)]">
                            <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-3">
                                Judge scores
                            </h3>
                            <JudgeScoreList scores={data.judge_scores} />
                        </section>

                        <section className="px-6 py-4 border-b border-[var(--color-border)]">
                            <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-3">
                                Turn intents
                            </h3>
                            {data.turn_intents.length > 0 ? (
                                <TurnIntentsTable intents={data.turn_intents} />
                            ) : (
                                <p className="text-xs text-[var(--color-muted)]">No turn intents.</p>
                            )}
                        </section>

                        <section className="px-6 py-4">
                            <TranscriptLink conversationId={data.conversation_id} />
                        </section>
                    </div>
                )}
            </SheetContent>
        </Sheet>
    )
}
