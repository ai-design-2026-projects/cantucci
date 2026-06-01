import { useState } from 'react'
import type { RunAggregateDto, SessionAggregateRowDto } from '@/api/dto/eval'
import { computeBoxStats, fmt } from '../../plots/stats'
import { colorForRun } from '../../plots/colors'
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, ErrorBar,
} from 'recharts'

type GroupBy = 'persona' | 'verbosity' | 'patience'

const METRIC_OPTIONS: Array<{ key: keyof NonNullable<SessionAggregateRowDto['metrics']>; label: string; fmt?: (v: number) => string }> = [
    { key: 'total_cost_usd', label: 'Cost (USD)', fmt: (v) => `$${v.toFixed(4)}` },
    { key: 'num_turns', label: 'Turns' },
]

const RATING_KEY = 'oracle_rating'
const JUDGE_KEY = 'judge_avg'

interface PersonaStatsSectionProps {
    aggregates: RunAggregateDto[]
}

function patienceBucket(p: number | null): string {
    if (p == null) return 'unknown'
    if (p < 0.35) return 'low (<0.35)'
    if (p < 0.65) return 'medium (0.35-0.65)'
    return 'high (>0.65)'
}

/**
 * Groups sessions by persona / verbosity / patience bucket and shows
 * horizontal bars of key metrics with CI per group.
 * Only renders in single-run mode (uses persona fields from the aggregate).
 */
export function PersonaStatsSection({ aggregates }: PersonaStatsSectionProps) {
    const [groupBy, setGroupBy] = useState<GroupBy>('persona')
    const [metric, setMetric] = useState<string>('total_cost_usd')

    if (aggregates.length !== 1) {
        return (
            <p className="text-xs text-[var(--color-muted)]">
                Persona stats are available in single-run view only.
            </p>
        )
    }

    const agg = aggregates[0]
    const sessions = agg.sessions.filter((s) => s.persona_slug != null)

    if (sessions.length === 0) {
        return (
            <p className="text-xs text-[var(--color-muted)]">
                No persona data available for this run.
            </p>
        )
    }

    const getGroupKey = (s: SessionAggregateRowDto): string => {
        if (groupBy === 'persona') return s.persona_slug ?? 'unknown'
        if (groupBy === 'verbosity') return s.persona_verbosity ?? 'unknown'
        return patienceBucket(s.persona_patience)
    }

    const getValue = (s: SessionAggregateRowDto): number | null => {
        if (metric === RATING_KEY) return s.oracle_rating ?? null
        if (metric === JUDGE_KEY) {
            const scores = s.judge_scores.map((j) => j.score)
            return scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : null
        }
        const mk = METRIC_OPTIONS.find((m) => m.key === metric)
        if (!mk) return null
        const v = s.metrics?.[mk.key]
        return v != null ? (v as number) : null
    }

    const groups: Record<string, number[]> = {}
    for (const s of sessions) {
        const key = getGroupKey(s)
        const val = getValue(s)
        if (val != null) {
            if (!groups[key]) groups[key] = []
            groups[key].push(val)
        }
    }

    const selectedMetricDef = METRIC_OPTIONS.find((m) => m.key === metric)
    const fmtVal = selectedMetricDef?.fmt ?? fmt

    const chartData = Object.entries(groups)
        .map(([group, values]) => {
            const stats = computeBoxStats(values)
            return {
                group,
                mean: stats?.mean ?? 0,
                ci: stats ? stats.ci95[1] - stats.mean : 0,
                n: values.length,
                stats,
            }
        })
        .sort((a, b) => b.mean - a.mean)

    const color = colorForRun(agg.run.id)

    return (
        <div className="flex flex-col gap-4">
            <div className="flex items-center gap-4 flex-wrap">
                <div className="flex items-center gap-2">
                    <span className="text-[10px] uppercase tracking-wide text-[var(--color-muted)]">Group by</span>
                    {(['persona', 'verbosity', 'patience'] as GroupBy[]).map((g) => (
                        <button
                            key={g}
                            onClick={() => setGroupBy(g)}
                            className={`text-[11px] px-2.5 py-0.5 rounded-full border transition-colors ${
                                groupBy === g
                                    ? 'bg-[var(--color-primary)] text-white border-[var(--color-primary)]'
                                    : 'border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-text)]'
                            }`}
                        >
                            {g}
                        </button>
                    ))}
                </div>

                <div className="flex items-center gap-2">
                    <span className="text-[10px] uppercase tracking-wide text-[var(--color-muted)]">Metric</span>
                    <select
                        className="text-xs bg-[var(--color-bg)] border border-[var(--color-border)] rounded px-1.5 py-0.5 text-[var(--color-text)] focus:outline-none"
                        value={metric}
                        onChange={(e) => setMetric(e.target.value)}
                    >
                        {METRIC_OPTIONS.map((m) => (
                            <option key={m.key} value={m.key}>{m.label}</option>
                        ))}
                        <option value={RATING_KEY}>Oracle Rating</option>
                        <option value={JUDGE_KEY}>Judge Avg</option>
                    </select>
                </div>
            </div>

            {chartData.length === 0 ? (
                <p className="text-xs text-[var(--color-muted)]">No data for this grouping.</p>
            ) : (
                <ResponsiveContainer width="100%" height={Math.max(120, chartData.length * 36 + 40)}>
                    <BarChart
                        data={chartData}
                        layout="vertical"
                        margin={{ left: 110, right: 60, top: 4, bottom: 4 }}
                    >
                        <CartesianGrid stroke="var(--color-border)" strokeOpacity={0.4} horizontal={false} />
                        <XAxis
                            type="number"
                            tick={{ fontSize: 9, fill: 'var(--color-muted)' }}
                            tickFormatter={(v) => fmtVal(v as number)}
                        />
                        <YAxis
                            type="category"
                            dataKey="group"
                            tick={{ fontSize: 10, fill: 'var(--color-text)' }}
                            width={108}
                        />
                        <Tooltip
                            contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', fontSize: 11 }}
                            formatter={(v, name) => {
                                if (name === 'mean') return [fmtVal(v as number), 'mean']
                                return [v, name]
                            }}
                            labelFormatter={(label, payload) => {
                                const n = payload?.[0]?.payload?.n as number | undefined
                                return `${label}${n != null ? ` (n=${n})` : ''}`
                            }}
                        />
                        <Bar dataKey="mean" radius={[0, 2, 2, 0]}>
                            <ErrorBar dataKey="ci" width={4} strokeWidth={1.5} stroke={color} direction="x" />
                            {chartData.map((_, i) => (
                                <Cell key={i} fill={color} opacity={0.85 - (i / chartData.length) * 0.3} />
                            ))}
                        </Bar>
                    </BarChart>
                </ResponsiveContainer>
            )}

            <p className="text-[10px] text-[var(--color-muted)]">
                Error bars show 95% confidence intervals of the mean. Groups without sufficient data (n=1) have no CI.
            </p>
        </div>
    )
}
