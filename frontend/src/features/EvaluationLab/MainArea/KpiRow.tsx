import type { RunAggregateDto } from '@/api/dto/eval'
import { computeBoxStats, fmt } from '../plots/stats'

interface KpiCardProps {
    label: string
    value: string
    sub?: string
}

function KpiCard({ label, value, sub }: KpiCardProps) {
    return (
        <div className="flex flex-col gap-0.5 p-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
            <span className="text-[10px] uppercase tracking-wider text-[var(--color-muted)]">{label}</span>
            <span className="text-xl font-bold text-[var(--color-text)]">{value}</span>
            {sub && <span className="text-[11px] text-[var(--color-muted)]">{sub}</span>}
        </div>
    )
}

interface KpiRowProps {
    aggregates: RunAggregateDto[]
}

/**
 * Row of 5 KPI cards for single-run or compare mode.
 * In single-run mode shows values with 95% CI of the mean where available.
 * In compare mode shows a mini table row per run.
 */
export function KpiRow({ aggregates }: KpiRowProps) {
    if (aggregates.length === 0) return null

    if (aggregates.length === 1) {
        const agg = aggregates[0]
        const sessions = agg.sessions
        const costs = sessions.flatMap((s) => (s.metrics ? [s.metrics.total_cost_usd] : []))
        const turns = sessions.flatMap((s) => (s.metrics ? [s.metrics.num_turns] : []))
        const ratings = sessions.flatMap((s) => (s.oracle_rating != null ? [s.oracle_rating] : []))

        const costStats = computeBoxStats(costs)
        const turnStats = computeBoxStats(turns)
        const ratingStats = computeBoxStats(ratings)
        const confidences = sessions.flatMap((s) => (s.mean_confidence != null ? [s.mean_confidence] : []))
        const confStats = computeBoxStats(confidences)
        const judgeScores = sessions.flatMap((s) => s.judge_scores.map((j) => j.score))
        const judgeStats = computeBoxStats(judgeScores)

        const pctCompleted = agg.summary.n_sessions > 0
            ? Math.round((agg.summary.n_completed / agg.summary.n_sessions) * 100)
            : 0

        return (
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
                <KpiCard
                    label="Sessions"
                    value={String(agg.summary.n_sessions)}
                    sub={`${agg.summary.n_completed} completed`}
                />
                <KpiCard
                    label="% Completed"
                    value={`${pctCompleted}%`}
                />
                <KpiCard
                    label="Mean Cost (USD)"
                    value={costStats ? fmt(costStats.mean) : '—'}
                    sub={costStats ? `± ${fmt(costStats.ci95[1] - costStats.mean)} 95% CI` : undefined}
                />
                <KpiCard
                    label="Mean Turns"
                    value={turnStats ? fmt(turnStats.mean) : '—'}
                    sub={turnStats ? `± ${fmt(turnStats.ci95[1] - turnStats.mean)} 95% CI` : undefined}
                />
                <KpiCard
                    label="Mean Oracle Rating"
                    value={ratingStats ? fmt(ratingStats.mean) : '—'}
                    sub={ratingStats ? `± ${fmt(ratingStats.ci95[1] - ratingStats.mean)} 95% CI` : undefined}
                />
                <KpiCard
                    label="Mean Judge Score"
                    value={judgeStats ? `${fmt(judgeStats.mean)} / 5` : '—'}
                    sub={judgeStats ? `± ${fmt(judgeStats.ci95[1] - judgeStats.mean)} 95% CI` : undefined}
                />
                <KpiCard
                    label="Mean Intent Confidence"
                    value={confStats ? `${Math.round(confStats.mean * 100)}%` : '—'}
                    sub={confStats ? `± ${Math.round((confStats.ci95[1] - confStats.mean) * 100)}pp 95% CI` : undefined}
                />
            </div>
        )
    }

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
                <thead>
                    <tr className="border-b border-[var(--color-border)]">
                        <th className="text-left py-2 px-3 text-[var(--color-muted)] font-medium">Run</th>
                        <th className="text-right py-2 px-3 text-[var(--color-muted)] font-medium">Sessions</th>
                        <th className="text-right py-2 px-3 text-[var(--color-muted)] font-medium">Completed %</th>
                        <th className="text-right py-2 px-3 text-[var(--color-muted)] font-medium">Mean Cost</th>
                        <th className="text-right py-2 px-3 text-[var(--color-muted)] font-medium">Mean Turns</th>
                        <th className="text-right py-2 px-3 text-[var(--color-muted)] font-medium">Oracle Rating</th>
                        <th className="text-right py-2 px-3 text-[var(--color-muted)] font-medium">Judge avg</th>
                        <th className="text-right py-2 px-3 text-[var(--color-muted)] font-medium">Confidence</th>
                    </tr>
                </thead>
                <tbody>
                    {aggregates.map((agg) => {
                        const sessions = agg.sessions
                        const costs = sessions.flatMap((s) => (s.metrics ? [s.metrics.total_cost_usd] : []))
                        const turns = sessions.flatMap((s) => (s.metrics ? [s.metrics.num_turns] : []))
                        const ratings = sessions.flatMap((s) => (s.oracle_rating != null ? [s.oracle_rating] : []))
                        const confidences = sessions.flatMap((s) => (s.mean_confidence != null ? [s.mean_confidence] : []))
                        const pct = agg.summary.n_sessions > 0
                            ? Math.round((agg.summary.n_completed / agg.summary.n_sessions) * 100)
                            : 0
                        const cStats = computeBoxStats(costs)
                        const tStats = computeBoxStats(turns)
                        const rStats = computeBoxStats(ratings)
                        const jScores = sessions.flatMap((s) => s.judge_scores.map((j) => j.score))
                        const jStats = computeBoxStats(jScores)
                        const cfStats = computeBoxStats(confidences)
                        return (
                            <tr key={agg.run.id} className="border-b border-[var(--color-border)] hover:bg-[var(--color-elevated)]">
                                <td className="py-1.5 px-3 font-medium">{agg.run.name ?? agg.run.id.slice(0, 8)}</td>
                                <td className="py-1.5 px-3 text-right">{agg.summary.n_sessions}</td>
                                <td className="py-1.5 px-3 text-right">{pct}%</td>
                                <td className="py-1.5 px-3 text-right font-mono">{cStats ? fmt(cStats.mean) : '—'}</td>
                                <td className="py-1.5 px-3 text-right font-mono">{tStats ? fmt(tStats.mean) : '—'}</td>
                                <td className="py-1.5 px-3 text-right font-mono">{rStats ? fmt(rStats.mean) : '—'}</td>
                                <td className="py-1.5 px-3 text-right font-mono">{jStats ? `${fmt(jStats.mean)} / 5` : '—'}</td>
                                <td className="py-1.5 px-3 text-right font-mono">{cfStats ? `${Math.round(cfStats.mean * 100)}%` : '—'}</td>
                            </tr>
                        )
                    })}
                </tbody>
            </table>
        </div>
    )
}
