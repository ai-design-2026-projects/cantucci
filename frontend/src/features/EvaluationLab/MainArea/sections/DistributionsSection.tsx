import type { RunAggregateDto, SessionAggregateRowDto } from '@/api/dto/eval'
import { BoxPlot } from '../../plots/BoxPlot'
import { computeBoxStats, fmt } from '../../plots/stats'
import { colorForRun } from '../../plots/colors'
import {
    BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
    Cell, Legend, PieChart, Pie,
} from 'recharts'

const METRIC_KEYS: Array<{ key: keyof NonNullable<SessionAggregateRowDto['metrics']>; label: string; fmt?: (v: number) => string }> = [
    { key: 'final_num_clusters', label: 'Clusters' },
    { key: 'clarifier_trigger_rate', label: 'Clarifier Rate', fmt: (v) => `${(v * 100).toFixed(1)}%` },
    { key: 'num_turns', label: 'Turns' },
    { key: 'num_operations', label: 'Operations' },
    { key: 'total_cost_usd', label: 'Cost (USD)', fmt: (v) => `$${v.toFixed(4)}` },
]

const STATUS_ORDER = ['active', 'finished_trajectory', 'finished_misbehaviour', 'finished_budget']
const STATUS_COLORS: Record<string, string> = {
    active: '#f59e0b',
    finished_trajectory: '#10b981',
    finished_misbehaviour: '#ef4444',
    finished_budget: '#8b5cf6',
}
const STATUS_LABELS: Record<string, string> = {
    active: 'Active',
    finished_trajectory: 'Trajectory',
    finished_misbehaviour: 'Misbehaviour',
    finished_budget: 'Budget',
}

const RATING_COLORS = ['#ef4444', '#f97316', '#eab308', '#84cc16', '#10b981']

interface DistributionsSectionProps {
    aggregates: RunAggregateDto[]
}

/** Single-run metric cards: mean value with ±CI text. */
function SingleRunMetrics({ agg }: { agg: RunAggregateDto }) {
    return (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {METRIC_KEYS.map(({ key, label, fmt: fmtFn }) => {
                const values = agg.sessions
                    .map((s) => s.metrics?.[key] as number | null | undefined)
                    .filter((v): v is number => v != null)
                const stats = computeBoxStats(values)
                return (
                    <div
                        key={key}
                        className="flex flex-col gap-1 p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]"
                    >
                        <span className="text-[10px] uppercase tracking-wide text-[var(--color-muted)]">{label}</span>
                        <span className="text-sm font-bold text-[var(--color-text)]">
                            {stats ? (fmtFn ? fmtFn(stats.mean) : fmt(stats.mean)) : '—'}
                        </span>
                        {stats && (
                            <span className="text-[10px] text-[var(--color-muted)]">
                                ± {fmtFn
                                    ? fmtFn(stats.ci95[1] - stats.mean)
                                    : fmt(stats.ci95[1] - stats.mean)} 95% CI
                            </span>
                        )}
                    </div>
                )
            })}
        </div>
    )
}

/** Diverging stacked bar of oracle ratings 1–5. */
function RatingCompositionBar({ agg }: { agg: RunAggregateDto }) {
    const ratings = agg.sessions.flatMap((s) => (s.oracle_rating != null ? [s.oracle_rating] : []))
    if (ratings.length === 0) return <p className="text-xs text-[var(--color-muted)]">No ratings.</p>

    const counts = [1, 2, 3, 4, 5].map((r) => ({ r, n: ratings.filter((v) => v === r).length }))
    const total = ratings.length

    return (
        <div className="flex flex-col gap-2">
            <div className="flex h-8 rounded overflow-hidden w-full">
                {counts.map(({ r, n }) => {
                    if (n === 0) return null
                    const pct = (n / total) * 100
                    return (
                        <div
                            key={r}
                            className="flex items-center justify-center text-white text-[9px] font-bold"
                            style={{ width: `${pct}%`, background: RATING_COLORS[r - 1] }}
                            title={`Rating ${r}: ${n} session${n !== 1 ? 's' : ''} (${pct.toFixed(0)}%)`}
                        >
                            {pct >= 10 ? r : ''}
                        </div>
                    )
                })}
            </div>
            <div className="flex gap-3 flex-wrap">
                {counts.map(({ r, n }) => n > 0 && (
                    <div key={r} className="flex items-center gap-1 text-[10px]">
                        <div className="h-2 w-2 rounded-full" style={{ background: RATING_COLORS[r - 1] }} />
                        <span className="text-[var(--color-muted)]">{r} — {n} ({((n / total) * 100).toFixed(0)}%)</span>
                    </div>
                ))}
            </div>
        </div>
    )
}

/** Single-run termination pie chart. */
function TerminationPie({ agg }: { agg: RunAggregateDto }) {
    const counts: Record<string, number> = {}
    for (const s of agg.sessions) {
        counts[s.status] = (counts[s.status] ?? 0) + 1
    }
    const data = STATUS_ORDER.filter((k) => counts[k] > 0).map((k) => ({
        name: STATUS_LABELS[k] ?? k,
        value: counts[k],
        fill: STATUS_COLORS[k],
    }))

    return (
        <ResponsiveContainer width="100%" height={220}>
            <PieChart margin={{ top: 8, right: 16, bottom: 16, left: 16 }}>
                <Pie
                    data={data}
                    cx="50%"
                    cy="45%"
                    innerRadius={45}
                    outerRadius={60}
                    dataKey="value"
                >
                    {data.map((entry) => (
                        <Cell key={entry.name} fill={entry.fill} />
                    ))}
                </Pie>
                <Tooltip
                    contentStyle={{
                        background: 'var(--color-surface)',
                        border: '1px solid var(--color-border)',
                        fontSize: 11,
                    }}
                    formatter={(v, name) => [v, name]}
                />
                <Legend
                    wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                    formatter={(value) => STATUS_LABELS[value] ?? value}
                />
            </PieChart>
        </ResponsiveContainer>
    )
}

/**
 * Distributions section.
 * Single-run: metric value cards with beeswarm, oracle rating composition bar,
 *             and termination pie chart.
 * Compare:    grouped box plots per metric, oracle rating histogram per run,
 *             and session termination stacked bar chart.
 */
export function DistributionsSection({ aggregates }: DistributionsSectionProps) {
    const isSingle = aggregates.length === 1

    if (isSingle) {
        const agg = aggregates[0]
        return (
            <div className="flex flex-col gap-8">
                <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-1">
                        Metric summary
                    </h3>
                    <p className="text-xs text-[var(--color-muted)] mb-4">
                        Mean value with 95% confidence interval across all sessions in this run. Each strip shows the spread of individual session values.
                    </p>
                    <SingleRunMetrics agg={agg} />
                </div>

                <div className="flex flex-col gap-6">
                    <div>
                        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-1">
                            Oracle rating breakdown
                        </h3>
                        <p className="text-xs text-[var(--color-muted)] mb-3">
                            Distribution of oracle self-ratings (1 to 5) across sessions. A rating of 5 means the oracle's intent was fully met.
                        </p>
                        <RatingCompositionBar agg={agg} />
                    </div>

                    <div>
                        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-1">
                            Session termination
                        </h3>
                        <p className="text-xs text-[var(--color-muted)] mb-3">
                            How sessions ended: trajectory means all GT operations were executed; misbehaviour means the oracle gave up; budget means the turn limit was reached.
                        </p>
                        <TerminationPie agg={agg} />
                    </div>
                </div>
            </div>
        )
    }

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

    const statusCounts: Record<string, Record<string, number>> = {}
    for (const agg of aggregates) {
        const runLabel = agg.run.name ?? agg.run.id.slice(0, 8)
        statusCounts[runLabel] = {}
        for (const s of agg.sessions) {
            statusCounts[runLabel][s.status] = (statusCounts[runLabel][s.status] ?? 0) + 1
        }
    }
    const statusChartData = Object.entries(statusCounts).map(([run, counts]) => ({ run, ...counts }))

    return (
        <div className="flex flex-col gap-8">
            <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-1">
                    Metric distributions
                </h3>
                <p className="text-xs text-[var(--color-muted)] mb-4">
                    Box plots grouped by run (box = Q1 to Q3, line = median, diamond = mean with 95% CI). Useful for spotting distribution differences between conditions.
                </p>
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
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-1">
                        Oracle rating breakdown
                    </h3>
                    <p className="text-xs text-[var(--color-muted)] mb-3">
                        Rating distribution per run shown as composition bars (1 to 5).
                    </p>
                    <div className="flex flex-col gap-3">
                        {aggregates.map((agg) => {
                            const ratings = agg.sessions.flatMap((s) => (s.oracle_rating != null ? [s.oracle_rating] : []))
                            const total = ratings.length
                            if (total === 0) return null
                            const counts = [1, 2, 3, 4, 5].map((r) => ({ r, n: ratings.filter((v) => v === r).length }))
                            return (
                                <div key={agg.run.id} className="flex flex-col gap-1">
                                    <div className="flex items-center gap-2">
                                        <div className="h-2 w-2 rounded-full shrink-0" style={{ background: colorForRun(agg.run.id) }} />
                                        <span className="text-[10px] text-[var(--color-muted)]">{agg.run.name ?? agg.run.id.slice(0, 8)}</span>
                                    </div>
                                    <div className="flex h-5 rounded overflow-hidden w-full">
                                        {counts.map(({ r, n }) => n > 0 && (
                                            <div
                                                key={r}
                                                className="flex items-center justify-center text-white text-[9px] font-bold"
                                                style={{ width: `${(n / total) * 100}%`, background: RATING_COLORS[r - 1] }}
                                                title={`${r}: ${n}`}
                                            >
                                                {(n / total) >= 0.1 ? r : ''}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )
                        })}
                    </div>
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
                                <Bar key={status} dataKey={status} name={STATUS_LABELS[status] ?? status} stackId="a" fill={STATUS_COLORS[status]} radius={0}>
                                    {statusChartData.map((_, i) => (
                                        <Cell key={i} fill={STATUS_COLORS[status]} />
                                    ))}
                                </Bar>
                            ))}
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    )
}
