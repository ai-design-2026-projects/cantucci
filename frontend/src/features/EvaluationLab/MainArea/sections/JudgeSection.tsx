import type { RunAggregateDto } from '@/api/dto/eval'
import { BoxPlot } from '../../plots/BoxPlot'
import { RadarPlot } from '../../plots/Radar'
import { computeBoxStats, fmt } from '../../plots/stats'
import { colorForRun } from '../../plots/colors'

const JUDGE_DIMENSIONS = [
    'operation_appropriateness',
    'label_accuracy',
    'suggestion_meaningfulness',
    'explanation_quality',
    'intent_alignment',
    'concept_axis_quality',
]

const DIMENSION_LABELS: Record<string, string> = {
    operation_appropriateness: 'Operation Appropriateness',
    label_accuracy: 'Label Accuracy',
    suggestion_meaningfulness: 'Suggestion Meaningfulness',
    explanation_quality: 'Explanation Quality',
    intent_alignment: 'Intent Alignment',
    concept_axis_quality: 'Concept Axis Quality',
}

const DIMENSION_DESCRIPTIONS: Record<string, string> = {
    operation_appropriateness: 'Did the system execute clustering operations that matched what the oracle asked for?',
    label_accuracy: 'Do the cluster labels and summaries accurately describe their member films?',
    suggestion_meaningfulness: 'Were proactive suggestions relevant and actionable given the current cluster state?',
    explanation_quality: 'Were explanations clear, accurate, and helpful to the oracle?',
    intent_alignment: 'Does the final clustering state reflect the oracle\'s overall intent?',
    concept_axis_quality: 'How well-formed were the bipolar concept axes built during the session? (Only scored when axes were created.)',
}

interface JudgeSectionProps {
    aggregates: RunAggregateDto[]
}

/**
 * Judge section. Single-run: radar chart + per-dimension mean±CI horizontal bars.
 * Compare: radar chart + per-dimension box plots.
 */
export function JudgeSection({ aggregates }: JudgeSectionProps) {
    const isSingle = aggregates.length === 1

    const activeDims = JUDGE_DIMENSIONS.filter((dim) =>
        aggregates.some((agg) =>
            agg.sessions.some((s) => s.judge_scores.some((j) => j.dimension === dim))
        )
    )

    const radarEntries = aggregates.map((agg) => {
        const scores: Record<string, { mean: number; ci95: [number, number] }> = {}
        for (const dim of activeDims) {
            const values = agg.sessions.flatMap((s) =>
                s.judge_scores.filter((j) => j.dimension === dim).map((j) => j.score)
            )
            const stats = computeBoxStats(values)
            scores[dim] = stats ? { mean: stats.mean, ci95: stats.ci95 } : { mean: 0, ci95: [0, 0] }
        }
        return {
            runId: agg.run.id,
            color: colorForRun(agg.run.id),
            label: agg.run.name ?? agg.run.id.slice(0, 8),
            scores,
        }
    })

    if (activeDims.length === 0) {
        return (
            <p className="text-xs text-[var(--color-muted)]">No judge scores recorded for this run.</p>
        )
    }

    return (
        <div className="flex flex-col gap-6">
            <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-1">
                    Judge scores overview
                </h3>
                <p className="text-xs text-[var(--color-muted)] mb-3">
                    Radar chart of mean scores per dimension (scale 1 to 5). Each polygon represents one run; overlapping polygons help compare conditions at a glance.
                </p>
                <RadarPlot entries={radarEntries} dimensions={activeDims} />
            </div>

            {isSingle ? (
                <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-1">
                        Per-dimension scores
                    </h3>
                    <p className="text-xs text-[var(--color-muted)] mb-4">
                        Mean score with 95% CI for each dimension. The shaded bar spans the CI; the label shows mean and CI half-width. Scores range from 1 (poor) to 5 (excellent).
                    </p>
                    <div className="flex flex-col gap-4">
                        {activeDims.map((dim) => {
                            const agg = aggregates[0]
                            const values = agg.sessions.flatMap((s) =>
                                s.judge_scores.filter((j) => j.dimension === dim).map((j) => j.score)
                            )
                            const stats = computeBoxStats(values)
                            const color = colorForRun(agg.run.id)
                            const meanPct = stats ? ((stats.mean - 1) / 4) * 100 : 0
                            const loPct = stats ? ((stats.ci95[0] - 1) / 4) * 100 : 0
                            const hiPct = stats ? ((stats.ci95[1] - 1) / 4) * 100 : 0

                            return (
                                <div key={dim} className="flex flex-col gap-1">
                                    <div className="flex items-baseline justify-between gap-2">
                                        <div>
                                            <span className="text-xs font-medium text-[var(--color-text)]">
                                                {DIMENSION_LABELS[dim] ?? dim}
                                            </span>
                                            <p className="text-[10px] text-[var(--color-muted)] mt-0.5">
                                                {DIMENSION_DESCRIPTIONS[dim]}
                                            </p>
                                        </div>
                                        <span className="text-sm font-bold text-[var(--color-text)] shrink-0">
                                            {stats ? `${fmt(stats.mean)}/5` : '—'}
                                        </span>
                                    </div>
                                    {stats && (
                                        <div className="relative h-3 bg-[var(--color-border)] rounded overflow-hidden">
                                            <div
                                                className="absolute top-0 bottom-0 rounded opacity-30"
                                                style={{
                                                    left: `${Math.max(0, loPct)}%`,
                                                    width: `${Math.min(100, hiPct) - Math.max(0, loPct)}%`,
                                                    background: color,
                                                }}
                                            />
                                            <div
                                                className="absolute top-0 bottom-0 w-0.5 rounded"
                                                style={{ left: `${meanPct}%`, background: color }}
                                            />
                                        </div>
                                    )}
                                    {stats && (
                                        <p className="text-[10px] text-[var(--color-muted)]">
                                            ± {fmt(stats.ci95[1] - stats.mean)} 95% CI ({values.length} session{values.length !== 1 ? 's' : ''})
                                        </p>
                                    )}
                                </div>
                            )
                        })}
                    </div>
                </div>
            ) : (
                <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-1">
                        Per-dimension distribution
                    </h3>
                    <p className="text-xs text-[var(--color-muted)] mb-4">
                        Box plots per dimension (Q1 to Q3 box, median line, mean diamond with 95% CI). Compare distributions side by side across runs.
                    </p>
                    <div className="flex flex-wrap gap-6 justify-center">
                        {activeDims.map((dim) => {
                            const entries = aggregates.map((agg) => {
                                const values = agg.sessions.flatMap((s) =>
                                    s.judge_scores.filter((j) => j.dimension === dim).map((j) => j.score)
                                )
                                const stats = computeBoxStats(values)
                                return stats
                                    ? { stats, color: colorForRun(agg.run.id), label: agg.run.name ?? agg.run.id.slice(0, 8) }
                                    : null
                            }).filter((e): e is NonNullable<typeof e> => e !== null)

                            return entries.length > 0 ? (
                                <BoxPlot
                                    key={dim}
                                    entries={entries}
                                    title={DIMENSION_LABELS[dim] ?? dim}
                                    height={160}
                                    width={110}
                                />
                            ) : null
                        })}
                    </div>
                </div>
            )}
        </div>
    )
}
