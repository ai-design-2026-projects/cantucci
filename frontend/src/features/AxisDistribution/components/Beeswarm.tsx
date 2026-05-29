import { useMemo } from 'react'
import {
    ScatterChart,
    Scatter,
    XAxis,
    YAxis,
    Tooltip,
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
}

function CustomDot({ cx = 0, cy = 0 }: CustomDotProps) {
    return (
        <circle
            cx={cx}
            cy={cy}
            r={4}
            fill="var(--color-accent)"
            fillOpacity={0.65}
            stroke="var(--color-accent)"
            strokeWidth={0.5}
        />
    )
}

interface BeeswarmProps {
    data: AxisDistributionDto
}

/**
 * Horizontal beeswarm plot of movie scores along a concept's linear axis.
 *
 * X axis spans [-1, 1] (normalized scores). Y axis shows swarm lanes computed
 * by a greedy collision-avoidance algorithm so dots don't overlap.
 *
 * @param data - Axis distribution with concept name and per-movie scored points.
 */
export function Beeswarm({ data }: BeeswarmProps) {
    const points = useMemo(() => computeBeeswarm(data.points), [data.points])

    if (points.length === 0) {
        return (
            <div className="flex items-center justify-center h-40 text-sm text-[var(--color-muted)]">
                No scores available.
            </div>
        )
    }

    const maxAbsLane = Math.max(...points.map((p) => Math.abs(p.lane)), 1)
    const yDomain = [-(maxAbsLane + 1), maxAbsLane + 1]

    return (
        <div className="w-full">
            <div className="flex justify-between text-xs text-[var(--color-muted)] px-8 mb-1 select-none">
                <span>← less {data.concept_name}</span>
                <span>more {data.concept_name} →</span>
            </div>
            <ResponsiveContainer width="100%" height={Math.max(120, (maxAbsLane * 2 + 3) * 18)}>
                <ScatterChart margin={{ top: 8, right: 24, bottom: 8, left: 24 }}>
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
                        dataKey="lane"
                        type="number"
                        domain={yDomain}
                        hide
                    />
                    <ReferenceLine x={0} stroke="var(--color-border)" strokeDasharray="4 4" />
                    <Tooltip content={<CustomTooltip />} cursor={false} />
                    <Scatter
                        data={points}
                        shape={<CustomDot />}
                    />
                </ScatterChart>
            </ResponsiveContainer>
        </div>
    )
}
