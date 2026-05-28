import {
    ScatterChart,
    Scatter,
    XAxis,
    YAxis,
    Tooltip,
    ResponsiveContainer,
    CartesianGrid,
    ReferenceLine,
} from 'recharts'
import { computeBoxStats } from './stats'

interface ScatterPoint {
    x: number
    y: number
    sessionId: string
    runId: string
    color: string
}

interface ScatterPlotProps {
    points: ScatterPoint[]
    xLabel: string
    yLabel: string
    onPointClick?: (sessionId: string) => void
}

interface CustomDotProps {
    cx?: number
    cy?: number
    payload?: ScatterPoint
    onPointClick?: (sessionId: string) => void
}

function CustomDot({ cx = 0, cy = 0, payload, onPointClick }: CustomDotProps) {
    if (!payload) return null
    return (
        <circle
            cx={cx}
            cy={cy}
            r={5}
            fill={payload.color}
            fillOpacity={0.75}
            stroke={payload.color}
            strokeWidth={1}
            style={{ cursor: onPointClick ? 'pointer' : 'default' }}
            onClick={() => onPointClick?.(payload.sessionId)}
        />
    )
}

/**
 * Scatter plot with 95% CI reference lines for each axis (mean ± CI shown as dashed lines).
 */
export function ScatterPlot({ points, xLabel, yLabel, onPointClick }: ScatterPlotProps) {
    if (points.length === 0) return null

    const xStats = computeBoxStats(points.map((p) => p.x))
    const yStats = computeBoxStats(points.map((p) => p.y))

    return (
        <div className="flex flex-col gap-1">
            <ResponsiveContainer width="100%" height={180}>
                <ScatterChart margin={{ top: 8, right: 16, bottom: 24, left: 32 }}>
                    <CartesianGrid stroke="var(--color-border)" strokeOpacity={0.4} />
                    <XAxis
                        dataKey="x"
                        type="number"
                        name={xLabel}
                        label={{ value: xLabel, position: 'insideBottom', offset: -8, fontSize: 10, fill: 'var(--color-muted)' }}
                        tick={{ fontSize: 10, fill: 'var(--color-muted)' }}
                    />
                    <YAxis
                        dataKey="y"
                        type="number"
                        name={yLabel}
                        label={{ value: yLabel, angle: -90, position: 'insideLeft', offset: 8, fontSize: 10, fill: 'var(--color-muted)' }}
                        tick={{ fontSize: 10, fill: 'var(--color-muted)' }}
                    />
                    <Tooltip
                        cursor={{ strokeDasharray: '3 3' }}
                        content={({ payload }) => {
                            const p = payload?.[0]?.payload as ScatterPoint | undefined
                            if (!p) return null
                            return (
                                <div className="text-xs p-2 bg-[var(--color-surface)] border border-[var(--color-border)] rounded shadow">
                                    <div>{xLabel}: {p.x.toFixed(3)}</div>
                                    <div>{yLabel}: {p.y.toFixed(3)}</div>
                                </div>
                            )
                        }}
                    />
                    {xStats && (
                        <>
                            <ReferenceLine x={xStats.mean} stroke="var(--color-muted)" strokeDasharray="4 2" strokeOpacity={0.6} />
                            <ReferenceLine x={xStats.ci95[0]} stroke="var(--color-muted)" strokeDasharray="2 4" strokeOpacity={0.35} />
                            <ReferenceLine x={xStats.ci95[1]} stroke="var(--color-muted)" strokeDasharray="2 4" strokeOpacity={0.35} />
                        </>
                    )}
                    {yStats && (
                        <>
                            <ReferenceLine y={yStats.mean} stroke="var(--color-muted)" strokeDasharray="4 2" strokeOpacity={0.6} />
                            <ReferenceLine y={yStats.ci95[0]} stroke="var(--color-muted)" strokeDasharray="2 4" strokeOpacity={0.35} />
                            <ReferenceLine y={yStats.ci95[1]} stroke="var(--color-muted)" strokeDasharray="2 4" strokeOpacity={0.35} />
                        </>
                    )}
                    <Scatter
                        data={points}
                        shape={(props: unknown) => <CustomDot {...(props as CustomDotProps)} onPointClick={onPointClick} />}
                    />
                </ScatterChart>
            </ResponsiveContainer>
        </div>
    )
}
