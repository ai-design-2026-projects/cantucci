import type { RunAggregateDto } from '@/api/dto/eval'
import { colorForRun } from '../../plots/colors'
import { computeBoxStats } from '../../plots/stats'
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, Legend, BarChart, Bar, Cell,
} from 'recharts'

interface CostSectionProps {
    aggregates: RunAggregateDto[]
}

/**
 * Cost section.
 * Single-run: sorted per-session cost Pareto bars to surface expensive outliers,
 *             and a cumulative cost line.
 * Compare:    mean cost per run and cumulative cost lines.
 */
export function CostSection({ aggregates }: CostSectionProps) {
    const isSingle = aggregates.length === 1

    const cumulativeData = (() => {
        const maxLen = Math.max(...aggregates.map((a) => a.sessions.length), 0)
        return Array.from({ length: maxLen }, (_, i) => {
            const point: Record<string, number | string> = { index: i + 1 }
            for (const agg of aggregates) {
                const sorted = [...agg.sessions].sort(
                    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
                )
                const cumCost = sorted.slice(0, i + 1).reduce((s, sess) => s + (sess.metrics?.total_cost_usd ?? 0), 0)
                point[agg.run.id] = cumCost
            }
            return point
        })
    })()

    return (
        <div className="flex flex-col gap-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {isSingle ? (
                    <div>
                        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-1">
                            Cost by session (sorted)
                        </h3>
                        <p className="text-xs text-[var(--color-muted)] mb-3">
                            Sessions ranked from highest to lowest cost. Long bars indicate expensive outlier sessions worth investigating.
                        </p>
                        {(() => {
                            const color = colorForRun(aggregates[0].run.id)
                            const costs = aggregates[0].sessions
                                .filter((s) => s.metrics != null)
                                .map((s) => ({ id: s.eval_session_id.slice(0, 6), cost: s.metrics!.total_cost_usd }))
                                .sort((a, b) => b.cost - a.cost)

                            return (
                                <ResponsiveContainer width="100%" height={220}>
                                    <BarChart data={costs} layout="vertical" margin={{ left: 8, right: 16, top: 8, bottom: 28 }}>
                                        <XAxis type="number" tick={{ fontSize: 9, fill: 'var(--color-muted)' }} tickFormatter={(v) => `$${v.toFixed(3)}`} />
                                        <YAxis type="category" dataKey="id" tick={{ fontSize: 9, fill: 'var(--color-muted)' }} width={56} />
                                        <Tooltip
                                            contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', fontSize: 11 }}
                                            formatter={(v) => [`$${(v as number).toFixed(5)}`, 'cost']}
                                        />
                                        <Bar dataKey="cost" radius={[0, 2, 2, 0]}>
                                            {costs.map((_, i) => (
                                                <Cell key={i} fill={color} opacity={1 - (i / costs.length) * 0.5} />
                                            ))}
                                        </Bar>
                                    </BarChart>
                                </ResponsiveContainer>
                            )
                        })()}
                    </div>
                ) : (
                    <div>
                        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-1">
                            Mean session cost per run
                        </h3>
                        <p className="text-xs text-[var(--color-muted)] mb-3">
                            Mean cost with 95% CI across sessions, per run.
                        </p>
                        <div className="flex flex-col gap-2">
                            {aggregates.map((agg) => {
                                const costs = agg.sessions.flatMap((s) => (s.metrics ? [s.metrics.total_cost_usd] : []))
                                const st = computeBoxStats(costs)
                                return (
                                    <div key={agg.run.id} className="flex items-center gap-3">
                                        <div className="h-2 w-2 rounded-full shrink-0" style={{ background: colorForRun(agg.run.id) }} />
                                        <span className="text-xs">{agg.run.name ?? agg.run.id.slice(0, 8)}</span>
                                        <span className="text-xs font-mono ml-auto">
                                            {st ? `$${st.mean.toFixed(4)} ± ${(st.ci95[1] - st.mean).toFixed(4)}` : '—'}
                                        </span>
                                    </div>
                                )
                            })}
                        </div>
                    </div>
                )}

                <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-1">
                        Cumulative cost
                    </h3>
                    <p className="text-xs text-[var(--color-muted)] mb-3">
                        Running total cost as sessions complete, ordered by creation time. Steep ramps indicate a cluster of expensive sessions.
                    </p>
                    <ResponsiveContainer width="100%" height={220}>
                        <LineChart data={cumulativeData} margin={{ top: 8, right: 16, bottom: 28, left: 8 }}>
                            <CartesianGrid stroke="var(--color-border)" strokeOpacity={0.4} />
                            <XAxis
                                dataKey="index"
                                label={{ value: 'Session #', position: 'insideBottom', offset: -8, fontSize: 10, fill: 'var(--color-muted)' }}
                                tick={{ fontSize: 10, fill: 'var(--color-muted)' }}
                            />
                            <YAxis
                                width={56}
                                tickFormatter={(v) => `$${(v as number).toFixed(2)}`}
                                tick={{ fontSize: 9, fill: 'var(--color-muted)' }}
                            />
                            <Tooltip
                                contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', fontSize: 11 }}
                                formatter={(v) => [typeof v === 'number' ? `$${v.toFixed(4)}` : v, 'cumulative']}
                            />
                            {aggregates.length > 1 && <Legend wrapperStyle={{ fontSize: 10 }} />}
                            {aggregates.map((agg) => (
                                <Line
                                    key={agg.run.id}
                                    type="monotone"
                                    dataKey={agg.run.id}
                                    name={agg.run.name ?? agg.run.id.slice(0, 8)}
                                    stroke={colorForRun(agg.run.id)}
                                    strokeWidth={2}
                                    dot={false}
                                />
                            ))}
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    )
}
