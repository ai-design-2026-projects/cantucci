import type { RunAggregateDto } from '@/api/dto/eval'
import { Histogram } from '../../plots/Histogram'
import { colorForRun } from '../../plots/colors'
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, Legend, ReferenceLine,
} from 'recharts'
import { computeBoxStats } from '../../plots/stats'

interface CostSectionProps {
    aggregates: RunAggregateDto[]
}

/**
 * Cost section: histogram of per-session cost and a cumulative cost timeline
 * (sessions sorted by created_at). In compare mode each run gets its own line.
 */
export function CostSection({ aggregates }: CostSectionProps) {
    const isSingle = aggregates.length === 1

    const singleCosts = isSingle
        ? aggregates[0].sessions.flatMap((s) => (s.metrics ? [s.metrics.total_cost_usd] : []))
        : []

    const cumulativeData = (() => {
        const maxLen = Math.max(...aggregates.map((a) => a.sessions.length), 0)
        return Array.from({ length: maxLen }, (_, i) => {
            const point: Record<string, number | string> = { index: i + 1 }
            for (const agg of aggregates) {
                const sessionsSorted = [...agg.sessions]
                    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
                const slice = sessionsSorted.slice(0, i + 1)
                const cumCost = slice.reduce((s, sess) => s + (sess.metrics?.total_cost_usd ?? 0), 0)
                point[agg.run.id] = cumCost
            }
            return point
        })
    })()

    const stats = computeBoxStats(singleCosts)

    return (
        <div className="flex flex-col gap-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {isSingle ? (
                    <div>
                        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-3">
                            Per-session cost distribution
                        </h3>
                        <Histogram
                            values={singleCosts}
                            color={colorForRun(aggregates[0].run.id)}
                            label="Cost (USD)"
                        />
                    </div>
                ) : (
                    <div>
                        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-3">
                            Mean session cost per run
                        </h3>
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
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)] mb-3">
                        Cumulative cost timeline
                    </h3>
                    <ResponsiveContainer width="100%" height={180}>
                        <LineChart data={cumulativeData} margin={{ top: 8, right: 16, bottom: 20, left: 40 }}>
                            <CartesianGrid stroke="var(--color-border)" strokeOpacity={0.4} />
                            <XAxis
                                dataKey="index"
                                label={{ value: 'Session #', position: 'insideBottom', offset: -8, fontSize: 10, fill: 'var(--color-muted)' }}
                                tick={{ fontSize: 10, fill: 'var(--color-muted)' }}
                            />
                            <YAxis
                                label={{ value: 'Cum. USD', angle: -90, position: 'insideLeft', offset: 8, fontSize: 10, fill: 'var(--color-muted)' }}
                                tick={{ fontSize: 10, fill: 'var(--color-muted)' }}
                            />
                            <Tooltip
                                contentStyle={{
                                    background: 'var(--color-surface)',
                                    border: '1px solid var(--color-border)',
                                    fontSize: 11,
                                }}
                                formatter={(v) => [typeof v === 'number' ? `$${v.toFixed(4)}` : v, 'cumulative']}
                            />
                            {aggregates.length > 1 && <Legend wrapperStyle={{ fontSize: 10 }} />}
                            {isSingle && stats && (
                                <>
                                    <ReferenceLine y={stats.mean} stroke={colorForRun(aggregates[0].run.id)} strokeDasharray="4 2" strokeOpacity={0.6} />
                                </>
                            )}
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
