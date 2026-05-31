import { useMemo } from 'react'
import {
    ScatterChart,
    Scatter,
    XAxis,
    YAxis,
    Tooltip,
    CartesianGrid,
    ResponsiveContainer,
    ReferenceLine,
} from 'recharts'

import type { AxisDistributionDto } from '@/api/dto/concepts'
import { computeBeeswarm } from '../lib/beeswarm'
import type { BeeswarmPoint } from '../lib/beeswarm'

interface TooltipPayloadEntry {
    payload: BeeswarmPoint
}

interface CustomTooltipProps {
    active?: boolean
    payload?: TooltipPayloadEntry[]
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
    if (!active || !payload?.length) return null
    const p = payload[0].payload
    return (
        <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1.5 text-xs shadow-md">
            <p className="font-medium leading-snug">{p.title}</p>
            <p className="text-[var(--color-muted)] mt-0.5">score: {p.score.toFixed(3)}</p>
        </div>
    )
}

interface CustomDotProps {
    cx?: number
    cy?: number
    payload?: BeeswarmPoint
}

function CustomDot({ cx = 0, cy = 0, payload }: CustomDotProps) {
    if (!payload) return null
    if (payload.isPolestar) {
        return (
            <circle
                cx={cx}
                cy={cy}
                r={8}
                data-axis-movie-title={payload.title}
                data-axis-score={payload.score}
                aria-label={`${payload.title} axis score ${payload.score.toFixed(3)}`}
                fill="var(--color-primary)"
                fillOpacity={0.95}
                stroke="var(--color-primary)"
                strokeWidth={1.5}
            />
        )
    }
    return (
        <circle
            cx={cx}
            cy={cy}
            r={5}
            data-axis-movie-title={payload.title}
            data-axis-score={payload.score}
            aria-label={`${payload.title} axis score ${payload.score.toFixed(3)}`}
            fill="var(--color-accent)"
            fillOpacity={0.45}
            stroke="none"
        />
    )
}

interface DensityRidgeProps {
    data: AxisDistributionDto
}

/**
 * Beeswarm plot of movie scores along a concept's linear axis.
 *
 * Each movie is placed at its score on the x-axis. The vertical position is
 * density-proportional jitter: the band width at each x-position scales with
 * the local point density, producing an organic swarm silhouette without
 * encoding anything on the y-axis.
 *
 * Pole-representative movies (high |score| AND high vote_count) are rendered
 * in a distinct color on top of the regular dots.
 *
 * @param data - Axis distribution with concept name, pole labels, and per-movie scored points.
 */
export function DensityRidge({ data }: DensityRidgeProps) {
    const allPoints = useMemo(() => computeBeeswarm(data.points), [data.points])
    const regularPoints = useMemo(() => allPoints.filter((p) => !p.isPolestar), [allPoints])
    const polestarPoints = useMemo(() => allPoints.filter((p) => p.isPolestar), [allPoints])

    if (allPoints.length === 0) {
        return (
            <div className="flex items-center justify-center h-40 text-sm text-[var(--color-muted)]">
                No scores available.
            </div>
        )
    }

    const negativeLabel = data.negative_label || `less ${data.concept_name}`
    const positiveLabel = data.positive_label || `more ${data.concept_name}`

    return (
        <div className="w-full">
            <div className="flex justify-between text-xs text-[var(--color-muted)] px-8 mb-1 select-none">
                <span>◀ {negativeLabel}</span>
                <span>{positiveLabel} ▶</span>
            </div>
            <ResponsiveContainer width="100%" height={420}>
                <ScatterChart margin={{ top: 8, right: 24, bottom: 8, left: 24 }}>
                    <CartesianGrid
                        strokeDasharray="4 4"
                        stroke="var(--color-border)"
                        strokeOpacity={0.35}
                    />
                    <XAxis
                        dataKey="score"
                        type="number"
                        domain={[-1, 1]}
                        tickCount={5}
                        tick={{ fontSize: 10 }}
                        tickLine={false}
                        axisLine={{ stroke: 'var(--color-border)' }}
                    />
                    <YAxis
                        dataKey="y"
                        type="number"
                        domain={[-1, 1]}
                        hide
                    />
                    <ReferenceLine x={0} stroke="var(--color-border)" strokeDasharray="4 4" />
                    <Tooltip content={<CustomTooltip />} cursor={false} />
                    <Scatter
                        data={regularPoints}
                        shape={<CustomDot />}
                        isAnimationActive={false}
                    />
                    <Scatter
                        data={polestarPoints}
                        shape={<CustomDot />}
                        isAnimationActive={false}
                    />
                </ScatterChart>
            </ResponsiveContainer>
        </div>
    )
}
