import type { RunAggregateDto, SessionAggregateRowDto } from '@/api/dto/eval'
import { BoxPlot } from '../../plots/BoxPlot'
import { Histogram } from '../../plots/Histogram'
import { ScatterPlot } from '../../plots/Scatter'
import { computeBoxStats } from '../../plots/stats'
import { colorForRun } from '../../plots/colors'
import { useEvalLabStore } from '../../hooks/useEvalLabStore'
import {
    BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell, Legend,
} from 'recharts'

const METRIC_KEYS: Array<{ key: keyof NonNullable<SessionAggregateRowDto['metrics']>; label: string }> = [
    { key: 'silhouette', label: 'Silhouette' },
    { key: 'mean_membership_prob', label: 'Membership prob' },
    { key: 'noise_fraction', label: 'Noise fraction' },
    { key: 'final_num_clusters', label: 'Num clusters' },
    { key: 'operation_recall', label: 'Op recall' },
    { key: 'clarifier_trigger_rate', label: 'Clarifier rate' },
    { key: 'num_turns', label: 'Turns' },
    { key: 'num_operations', label: 'Operations' },
    { key: 'total_cost_usd', label: 'Cost (USD)' },
]

const STATUS_ORDER = ['active', 'finished_trajectory', 'finished_misbehaviour', 'finished_budget']
const STATUS_COLORS: Record<string, string> = {
    active: '#f59e0b',
    finished_trajectory: '#10b981',
    finished_misbehaviour: '#ef4444',
    finished_budget: '#8b5cf6',
}

interface DistributionsSectionProps {
    aggregates: RunAggregateDto[]
}

/**
 * Distributions section: box plots for 9 scalar metrics, oracle rating histogram,
 * session status stacked bar, and 3 scatter plots (cost↔turns, cost↔silhouette,
 * turns↔silhouette). In compare mode, box plots are grouped side by side per run.
 */
export function DistributionsSection({ aggregates }: DistributionsSectionProps) {
    const { setOpenSessionId } = useEvalLabStore()

    const boxEntries = METRIC_KEYS.map(({ key, label }) => ({
        key,
        label,
        perRun: aggregates.map((agg) => {
            const values = agg.sessions
                .map((s) => s.metrics?.[key] as number | null | undefined)
                .filter((v): v is number => v != null)
            const stats = computeBoxStats(values)
            return { stats, color: colorForRun(agg.run.id), label: agg.run.name ?? agg.run.id.slice(0, 8) }
        }).filter((e) => e.stats !== null) as Array<{ stats: NonNullable<ReturnType<typeof computeBoxStats>>; color: string; label: string }>,
    }))

    const oracleRatings = aggregates.flatMap((agg) =>
        agg.sessions.flatMap((s) => (s.oracle_rating != null ? [s.oracle_rating] : []))
    )

    const statusCounts: Record<string, Record<string, number>> = {}
    for (const agg of aggregates) {
        const runLabel = agg.run.name ?? agg.run.id.slice(0, 8)
        statusCounts[runLabel] = {}
        for (const s of agg.sessions) {
            statusCounts[runLabel][s.status] = (statusCounts[runLabel][s.status] ?? 0) + 1
        }
    }
    const statusChartData = Object.entries(statusCounts).map(([run, counts]) => ({ run, ...counts }))

    const scatterSets = [
        {
            label: 'Cost ↔ Turns',
            xKey: 'total_cost_usd' as const,
            yKey: 'num_turns' as const,
            xLabel: 'Cost (USD)',
            yLabel: 'Turns',
        },
        {
            label: 'Cost ↔ Silhouette',
            xKey: 'total_cost_usd' as const,
            yKey: 'silhouette' as const,
            xLabel: 'Cost (USD)',
            yLabel: 'Silhouette',
        },
        {
            label: 'Turns ↔ Silhouette',
            xKey: 'num_turns' as const,
            yKey: 'silhouette' as const,
            xLabel: 'Turns',
            yLabel: 'Silhouette',
        },
    ]

    return (
        <div className="flex flex-col gap-8">
            <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-4">
                    Metric distributions
                    <span className="normal-case font-normal ml-1">(box = Q1–Q3, line = median, ◆ = mean ± 95% CI)</span>
                </h3>
                <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4 justify-items-center">
                    {boxEntries.map(({ label, perRun }) =>
                        perRun.length > 0 ? (
                            <BoxPlot key={label} entries={perRun} title={label} />
                        ) : null
                    )}
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-3">
                        Oracle rating distribution
                    </h3>
                    <Histogram values={oracleRatings} bins={5} ordinal color="#f59e0b" />
                </div>

                <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-3">
                        Session termination
                    </h3>
                    <ResponsiveContainer width="100%" height={140}>
                        <BarChart data={statusChartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
                            <CartesianGrid stroke="var(--color-border)" strokeOpacity={0.4} vertical={false} />
                            <XAxis dataKey="run" tick={{ fontSize: 10, fill: 'var(--color-muted)' }} />
                            <YAxis tick={{ fontSize: 9, fill: 'var(--color-muted)' }} allowDecimals={false} />
                            <Tooltip
                                contentStyle={{
                                    background: 'var(--color-surface)',
                                    border: '1px solid var(--color-border)',
                                    fontSize: 11,
                                }}
                            />
                            <Legend wrapperStyle={{ fontSize: 10 }} />
                            {STATUS_ORDER.map((status) => (
                                <Bar key={status} dataKey={status} stackId="a" fill={STATUS_COLORS[status]} radius={0}>
                                    {statusChartData.map((_, i) => (
                                        <Cell key={i} fill={STATUS_COLORS[status]} />
                                    ))}
                                </Bar>
                            ))}
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-4">
                    Scatter plots
                    <span className="normal-case font-normal ml-1">(dashed = mean ± 95% CI per axis; click dot to open session)</span>
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    {scatterSets.map(({ label, xKey, yKey, xLabel, yLabel }) => {
                        const points = aggregates.flatMap((agg) =>
                            agg.sessions.flatMap((s) => {
                                const x = s.metrics?.[xKey]
                                const y = s.metrics?.[yKey]
                                if (x == null || y == null) return []
                                return [{
                                    x: x as number,
                                    y: y as number,
                                    sessionId: s.eval_session_id,
                                    runId: agg.run.id,
                                    color: colorForRun(agg.run.id),
                                }]
                            })
                        )
                        return (
                            <div key={label} className="flex flex-col gap-1">
                                <span className="text-xs text-[var(--color-muted)]">{label}</span>
                                <ScatterPlot
                                    points={points}
                                    xLabel={xLabel}
                                    yLabel={yLabel}
                                    onPointClick={setOpenSessionId}
                                />
                            </div>
                        )
                    })}
                </div>
            </div>
        </div>
    )
}
