import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ReferenceLine,
    ResponsiveContainer,
} from 'recharts'
import type { TurnIntentDto } from '@/api/dto/eval'
import { computeBoxStats } from '../plots/stats'

interface PerTurnConfidenceChartProps {
    intents: TurnIntentDto[]
    color?: string
    height?: number
}

interface ChartDatum {
    turn: number
    confidence: number
    mode: string
    clarifier: boolean
}

/**
 * Line chart of intent confidence over turns for one session.
 * Clarifier-fired turns are marked with a vertical dashed reference line.
 * A horizontal dashed line shows the 95% CI of the mean confidence.
 */
export function PerTurnConfidenceChart({
    intents,
    color = '#6366f1',
    height = 200,
}: PerTurnConfidenceChartProps) {
    const data: ChartDatum[] = intents.map((t) => ({
        turn: t.turn_number,
        confidence: t.confidence,
        mode: t.mode,
        clarifier: t.clarifier_fired,
    }))

    const clarifierTurns = [...new Set(
        intents.filter((t) => t.clarifier_fired).map((t) => t.turn_number),
    )]

    const stats = computeBoxStats(data.map((d) => d.confidence))

    return (
        <ResponsiveContainer width="100%" height={height}>
            <LineChart data={data} margin={{ top: 8, right: 16, bottom: 20, left: 32 }}>
                <CartesianGrid stroke="var(--color-border)" strokeOpacity={0.4} />
                <XAxis
                    dataKey="turn"
                    type="number"
                    label={{ value: 'Turn', position: 'insideBottom', offset: -8, fontSize: 10, fill: 'var(--color-muted)' }}
                    tick={{ fontSize: 10, fill: 'var(--color-muted)' }}
                />
                <YAxis
                    domain={[0, 1]}
                    label={{ value: 'Confidence', angle: -90, position: 'insideLeft', offset: 8, fontSize: 10, fill: 'var(--color-muted)' }}
                    tick={{ fontSize: 10, fill: 'var(--color-muted)' }}
                />
                <Tooltip
                    contentStyle={{
                        background: 'var(--color-surface)',
                        border: '1px solid var(--color-border)',
                        fontSize: 11,
                    }}
                    formatter={(v, _name, entry) => [
                        typeof v === 'number' ? `${v.toFixed(3)} (${(entry.payload as ChartDatum | undefined)?.mode ?? ''})` : v,
                        'confidence',
                    ]}
                />
                {clarifierTurns.map((t) => (
                    <ReferenceLine
                        key={t}
                        x={t}
                        stroke="#ef4444"
                        strokeDasharray="4 2"
                        strokeWidth={1.5}
                        label={{ value: '▲', position: 'top', fontSize: 8, fill: '#ef4444' }}
                    />
                ))}
                {stats && (
                    <>
                        <ReferenceLine y={stats.mean} stroke={color} strokeDasharray="4 2" strokeOpacity={0.6} />
                        <ReferenceLine y={stats.ci95[0]} stroke={color} strokeDasharray="2 4" strokeOpacity={0.3} />
                        <ReferenceLine y={stats.ci95[1]} stroke={color} strokeDasharray="2 4" strokeOpacity={0.3} />
                    </>
                )}
                <Line
                    type="monotone"
                    dataKey="confidence"
                    stroke={color}
                    strokeWidth={2}
                    dot={{ r: 3, fill: color }}
                    activeDot={{ r: 5 }}
                />
            </LineChart>
        </ResponsiveContainer>
    )
}
