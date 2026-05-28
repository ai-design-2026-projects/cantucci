import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    Tooltip,
    ResponsiveContainer,
    ReferenceLine,
    CartesianGrid,
    Cell,
} from 'recharts'
import { histogram, computeBoxStats } from './stats'

interface HistogramProps {
    values: number[]
    color?: string
    bins?: number
    label?: string
    /** If true, each bar is a single ordinal integer label (e.g. 1–5 oracle rating). */
    ordinal?: boolean
}

/**
 * Histogram bar chart with mean reference line and 95% CI shading of the mean.
 * Ordinal mode renders one bar per integer value (useful for 1–5 Likert scales).
 */
export function Histogram({ values, color = '#6366f1', bins = 10, label, ordinal = false }: HistogramProps) {
    const stats = computeBoxStats(values)

    let data: Array<{ label: string; count: number }>

    if (ordinal) {
        const counts = new Map<number, number>()
        for (const v of values) {
            if (v != null) counts.set(v, (counts.get(v) ?? 0) + 1)
        }
        const keys = [...counts.keys()].sort((a, b) => a - b)
        data = keys.map((k) => ({ label: String(k), count: counts.get(k) ?? 0 }))
    } else {
        const buckets = histogram(values, bins)
        data = buckets.map((b) => ({
            label: `${b.x0.toFixed(2)}`,
            count: b.count,
        }))
    }

    return (
        <div className="flex flex-col gap-1">
            {label && <span className="text-xs text-[var(--color-muted)] font-medium">{label}</span>}
            <ResponsiveContainer width="100%" height={140}>
                <BarChart data={data} margin={{ top: 4, right: 8, bottom: 20, left: 24 }}>
                    <CartesianGrid stroke="var(--color-border)" strokeOpacity={0.4} vertical={false} />
                    <XAxis
                        dataKey="label"
                        tick={{ fontSize: 9, fill: 'var(--color-muted)' }}
                        interval="preserveStartEnd"
                    />
                    <YAxis tick={{ fontSize: 9, fill: 'var(--color-muted)' }} allowDecimals={false} />
                    <Tooltip
                        contentStyle={{
                            background: 'var(--color-surface)',
                            border: '1px solid var(--color-border)',
                            fontSize: 11,
                        }}
                        formatter={(v) => [v, 'sessions']}
                    />
                    {stats && (
                        <>
                            <ReferenceLine
                                x={ordinal ? String(Math.round(stats.mean)) : stats.mean.toFixed(2)}
                                stroke={color}
                                strokeDasharray="4 2"
                                strokeWidth={2}
                                label={{ value: `μ=${stats.mean.toFixed(2)}`, position: 'top', fontSize: 9, fill: color }}
                            />
                            {!ordinal && (
                                <>
                                    <ReferenceLine x={stats.ci95[0].toFixed(2)} stroke={color} strokeDasharray="2 4" strokeOpacity={0.45} />
                                    <ReferenceLine x={stats.ci95[1].toFixed(2)} stroke={color} strokeDasharray="2 4" strokeOpacity={0.45} />
                                </>
                            )}
                        </>
                    )}
                    <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                        {data.map((_, i) => (
                            <Cell key={i} fill={color} fillOpacity={0.75} />
                        ))}
                    </Bar>
                </BarChart>
            </ResponsiveContainer>
        </div>
    )
}
