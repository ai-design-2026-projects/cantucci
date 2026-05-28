import {
    RadarChart,
    PolarGrid,
    PolarAngleAxis,
    Radar,
    ResponsiveContainer,
    Tooltip,
} from 'recharts'

interface RadarEntry {
    runId: string
    color: string
    label: string
    /** Map dimension → { mean, ci95: [lo, hi] } */
    scores: Record<string, { mean: number; ci95: [number, number] }>
}

interface RadarPlotProps {
    entries: RadarEntry[]
    dimensions: string[]
}

/**
 * Multi-run radar chart of mean judge scores (1–5) per dimension.
 * Shaded area for each run's 95% CI of the mean per dimension.
 */
export function RadarPlot({ entries, dimensions }: RadarPlotProps) {
    const data = dimensions.map((dim) => {
        const point: Record<string, number | string> = { dim }
        for (const entry of entries) {
            point[entry.runId] = entry.scores[dim]?.mean ?? 0
            point[`${entry.runId}_ci_lo`] = entry.scores[dim]?.ci95[0] ?? 0
            point[`${entry.runId}_ci_hi`] = entry.scores[dim]?.ci95[1] ?? 0
        }
        return point
    })

    const formatLabel = (dim: string) =>
        dim.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

    return (
        <ResponsiveContainer width="100%" height={260}>
            <RadarChart data={data} margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
                <PolarGrid stroke="var(--color-border)" />
                <PolarAngleAxis
                    dataKey="dim"
                    tickFormatter={formatLabel}
                    tick={{ fontSize: 11, fill: 'var(--color-muted)' }}
                />
                <Tooltip
                    formatter={(value, name) => [typeof value === 'number' ? value.toFixed(2) : value, name]}
                    contentStyle={{
                        background: 'var(--color-surface)',
                        border: '1px solid var(--color-border)',
                        fontSize: 12,
                    }}
                />
                {entries.map((entry) => (
                    <Radar
                        key={entry.runId}
                        name={entry.label}
                        dataKey={entry.runId}
                        stroke={entry.color}
                        fill={entry.color}
                        fillOpacity={0.12}
                        strokeWidth={2}
                        dot={{ r: 3, fill: entry.color }}
                    />
                ))}
            </RadarChart>
        </ResponsiveContainer>
    )
}
