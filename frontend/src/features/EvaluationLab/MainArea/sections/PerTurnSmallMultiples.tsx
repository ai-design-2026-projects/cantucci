import { useQueries } from '@tanstack/react-query'
import { getSessionDetailFetcher } from '@/api/services/eval'
import type { RunAggregateDto } from '@/api/dto/eval'
import { colorForRun } from '../../plots/colors'
import { useEvalLabStore } from '../../hooks/useEvalLabStore'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

interface PerTurnSmallMultiplesProps {
    aggregates: RunAggregateDto[]
}

interface MiniChartProps {
    sessionId: string
    color: string
    onClick: () => void
}

function MiniChart({ sessionId, color, onClick }: MiniChartProps) {
    const { data, isLoading } = useQueries({
        queries: [{
            queryKey: ['eval', 'session', sessionId],
            queryFn: () => getSessionDetailFetcher(sessionId),
            staleTime: Infinity,
        }],
    })[0]

    if (isLoading) {
        return (
            <div
                className="border border-[var(--color-border)] rounded p-2 flex items-center justify-center cursor-pointer hover:border-[var(--color-primary)] transition-colors"
                style={{ height: 90 }}
                onClick={onClick}
            >
                <div className="h-3 w-3 rounded-full border-2 border-[var(--color-primary)] border-t-transparent animate-spin" />
            </div>
        )
    }

    if (!data || data.turn_intents.length === 0) {
        return (
            <div
                className="border border-[var(--color-border)] rounded p-2 flex items-center justify-center cursor-pointer hover:border-[var(--color-primary)] transition-colors text-[10px] text-[var(--color-muted)]"
                style={{ height: 90 }}
                onClick={onClick}
            >
                no data
            </div>
        )
    }

    const chartData = data.turn_intents.map((t) => ({
        turn: t.turn_number,
        conf: t.confidence,
        clarifier: t.clarifier_fired,
    }))

    const clarifierTurns = [...new Set(
        data.turn_intents.filter((t) => t.clarifier_fired).map((t) => t.turn_number)
    )]

    return (
        <div
            className="border border-[var(--color-border)] rounded cursor-pointer hover:border-[var(--color-primary)] transition-colors overflow-hidden"
            style={{ height: 90 }}
            onClick={onClick}
            title={`Session ${sessionId.slice(0, 8)} — click to open`}
        >
            <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
                    <XAxis dataKey="turn" hide />
                    <YAxis domain={[0, 1]} hide />
                    <Tooltip
                        contentStyle={{ fontSize: 10, padding: '2px 6px' }}
                        formatter={(v) => [typeof v === 'number' ? v.toFixed(2) : v, 'conf']}
                    />
                    {clarifierTurns.map((t) => (
                        <ReferenceLine key={t} x={t} stroke="#ef4444" strokeWidth={1} strokeDasharray="2 2" />
                    ))}
                    <Line type="monotone" dataKey="conf" stroke={color} strokeWidth={1.5} dot={false} />
                </LineChart>
            </ResponsiveContainer>
        </div>
    )
}

/**
 * Small-multiples grid of per-session confidence timelines.
 * Each tile fetches its own session detail lazily; clicking opens the slide-over.
 * Hidden in compare mode (not meaningful across runs at this granularity).
 */
export function PerTurnSmallMultiples({ aggregates }: PerTurnSmallMultiplesProps) {
    const { setOpenSessionId, compareMode } = useEvalLabStore()

    if (compareMode) {
        return (
            <p className="text-xs text-[var(--color-muted)]">
                Per-turn timelines are hidden in compare mode — select a single run to explore individual sessions.
            </p>
        )
    }

    const agg = aggregates[0]
    if (!agg || agg.sessions.length === 0) {
        return <p className="text-xs text-[var(--color-muted)]">No sessions in this run.</p>
    }

    const color = colorForRun(agg.run.id)

    return (
        <div className="flex flex-col gap-3">
            <p className="text-[10px] text-[var(--color-muted)]">
                Each tile = one session. Red dashes = clarifier fired. Click to open session detail.
            </p>
            <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-2">
                {agg.sessions.map((s) => (
                    <MiniChart
                        key={s.eval_session_id}
                        sessionId={s.eval_session_id}
                        color={color}
                        onClick={() => setOpenSessionId(s.eval_session_id)}
                    />
                ))}
            </div>
        </div>
    )
}
