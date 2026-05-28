import type { RunAggregateDto } from '@/api/dto/eval'
import { BoxPlot } from '../../plots/BoxPlot'
import { RadarPlot } from '../../plots/Radar'
import { computeBoxStats } from '../../plots/stats'
import { colorForRun } from '../../plots/colors'

const JUDGE_DIMENSIONS = [
    'operation_appropriateness',
    'label_accuracy',
    'suggestion_meaningfulness',
    'explanation_quality',
    'intent_alignment',
]

interface JudgeSectionProps {
    aggregates: RunAggregateDto[]
}

/**
 * Judge section: radar chart of mean scores across 5 dimensions and per-dimension
 * box plots. In compare mode each run gets its own polygon on the radar.
 */
export function JudgeSection({ aggregates }: JudgeSectionProps) {
    const radarEntries = aggregates.map((agg) => {
        const scores: Record<string, { mean: number; ci95: [number, number] }> = {}
        for (const dim of JUDGE_DIMENSIONS) {
            const values = agg.sessions.flatMap((s) =>
                s.judge_scores
                    .filter((j) => j.dimension === dim)
                    .map((j) => j.score)
            )
            const stats = computeBoxStats(values)
            if (stats) {
                scores[dim] = { mean: stats.mean, ci95: stats.ci95 }
            } else {
                scores[dim] = { mean: 0, ci95: [0, 0] }
            }
        }
        return {
            runId: agg.run.id,
            color: colorForRun(agg.run.id),
            label: agg.run.name ?? agg.run.id.slice(0, 8),
            scores,
        }
    })

    const boxEntriesPerDim = JUDGE_DIMENSIONS.map((dim) => ({
        dim,
        entries: aggregates.map((agg) => {
            const values = agg.sessions.flatMap((s) =>
                s.judge_scores.filter((j) => j.dimension === dim).map((j) => j.score)
            )
            const stats = computeBoxStats(values)
            return stats ? { stats, color: colorForRun(agg.run.id), label: agg.run.name ?? agg.run.id.slice(0, 8) } : null
        }).filter((e): e is NonNullable<typeof e> => e !== null),
    }))

    const formatDim = (d: string) =>
        d.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

    return (
        <div className="flex flex-col gap-6">
            <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-3">
                    Mean judge scores — radar
                </h3>
                <RadarPlot entries={radarEntries} dimensions={JUDGE_DIMENSIONS} />
            </div>

            <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-4">
                    Per-dimension distribution
                    <span className="normal-case font-normal ml-1">(box = Q1–Q3, ◆ = mean ± 95% CI)</span>
                </h3>
                <div className="flex flex-wrap gap-6 justify-center">
                    {boxEntriesPerDim.map(({ dim, entries }) =>
                        entries.length > 0 ? (
                            <BoxPlot key={dim} entries={entries} title={formatDim(dim)} height={160} width={110} />
                        ) : null
                    )}
                </div>
            </div>
        </div>
    )
}
