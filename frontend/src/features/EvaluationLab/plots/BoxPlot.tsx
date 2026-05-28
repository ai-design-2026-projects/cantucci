import type { BoxStats } from './stats'

interface BoxEntry {
    stats: BoxStats
    color: string
    label?: string
}

interface BoxPlotProps {
    entries: BoxEntry[]
    title: string
    height?: number
    width?: number
}

/**
 * Pure-SVG vertical box plot. Each entry renders a box (Q1–Q3), whiskers (min–max),
 * median line, and a 95% CI bar of the mean (diamond + interval bracket).
 *
 * Multiple entries are rendered side-by-side for compare mode.
 */
export function BoxPlot({ entries, title, height = 180, width = 120 }: BoxPlotProps) {
    if (entries.length === 0) return null

    const allValues = entries.flatMap((e) => [e.stats.min, e.stats.max, e.stats.ci95[0], e.stats.ci95[1]])
    const domainMin = Math.min(...allValues)
    const domainMax = Math.max(...allValues)
    const range = domainMax - domainMin || 1

    const pad = { top: 12, bottom: 28, left: 8, right: 8 }
    const plotH = height - pad.top - pad.bottom
    const plotW = width - pad.left - pad.right

    const toY = (v: number) => pad.top + plotH - ((v - domainMin) / range) * plotH

    const boxW = Math.max(14, Math.min(28, plotW / entries.length - 8))
    const slotW = plotW / entries.length

    return (
        <div className="flex flex-col items-center gap-1">
            <svg width={width} height={height} className="overflow-visible">
                {entries.map((entry, i) => {
                    const { stats, color } = entry
                    const cx = pad.left + slotW * i + slotW / 2
                    const y_min = toY(stats.min)
                    const y_q1 = toY(stats.q1)
                    const y_med = toY(stats.median)
                    const y_q3 = toY(stats.q3)
                    const y_max = toY(stats.max)
                    const y_mean = toY(stats.mean)
                    const y_ci_lo = toY(stats.ci95[0])
                    const y_ci_hi = toY(stats.ci95[1])
                    const hw = boxW / 2

                    return (
                        <g key={i}>
                            {/* whisker lines */}
                            <line x1={cx} y1={y_min} x2={cx} y2={y_q1} stroke={color} strokeWidth={1.5} strokeDasharray="2 2" />
                            <line x1={cx} y1={y_q3} x2={cx} y2={y_max} stroke={color} strokeWidth={1.5} strokeDasharray="2 2" />
                            {/* whisker caps */}
                            <line x1={cx - hw * 0.5} y1={y_min} x2={cx + hw * 0.5} y2={y_min} stroke={color} strokeWidth={1.5} />
                            <line x1={cx - hw * 0.5} y1={y_max} x2={cx + hw * 0.5} y2={y_max} stroke={color} strokeWidth={1.5} />
                            {/* box Q1–Q3 */}
                            <rect
                                x={cx - hw}
                                y={y_q3}
                                width={boxW}
                                height={Math.max(1, y_q1 - y_q3)}
                                fill={color}
                                fillOpacity={0.18}
                                stroke={color}
                                strokeWidth={1.5}
                                rx={2}
                            />
                            {/* median line */}
                            <line x1={cx - hw} y1={y_med} x2={cx + hw} y2={y_med} stroke={color} strokeWidth={2.5} />
                            {/* 95% CI bracket of the mean */}
                            <line x1={cx} y1={y_ci_hi} x2={cx} y2={y_ci_lo} stroke={color} strokeWidth={1} strokeOpacity={0.7} />
                            <line x1={cx - 3} y1={y_ci_hi} x2={cx + 3} y2={y_ci_hi} stroke={color} strokeWidth={1} strokeOpacity={0.7} />
                            <line x1={cx - 3} y1={y_ci_lo} x2={cx + 3} y2={y_ci_lo} stroke={color} strokeWidth={1} strokeOpacity={0.7} />
                            {/* mean diamond */}
                            <polygon
                                points={`${cx},${y_mean - 4} ${cx + 4},${y_mean} ${cx},${y_mean + 4} ${cx - 4},${y_mean}`}
                                fill={color}
                                stroke="var(--color-surface)"
                                strokeWidth={1}
                            />
                        </g>
                    )
                })}
                {/* axis ticks */}
                {[0, 0.5, 1].map((t) => {
                    const v = domainMin + t * range
                    const y = toY(v)
                    return (
                        <g key={t}>
                            <line x1={pad.left - 3} y1={y} x2={pad.left} y2={y} stroke="var(--color-muted)" strokeWidth={1} />
                            <text
                                x={pad.left - 4}
                                y={y + 4}
                                fontSize={9}
                                fill="var(--color-muted)"
                                textAnchor="end"
                            >
                                {v.toFixed(2)}
                            </text>
                        </g>
                    )
                })}
            </svg>
            <span className="text-[10px] text-[var(--color-muted)] text-center leading-tight px-1">{title}</span>
        </div>
    )
}
