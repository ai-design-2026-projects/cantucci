import { useRef, useState, useEffect, useMemo } from 'react'
import { clusterColorFromUuid } from '@/styles/theme'
import { useThemeStore } from '@/store/useThemeStore'
import type { ClusterSnapshotDto } from '@/api/dto/snapshots'
import type { ScatterPoint } from '../hooks/useScatterData.ts'
import { useSnapshotPlotData } from '../hooks/useSnapshotPlotData.ts'
import { useCanvasScatterPlot } from '../hooks/useCanvasScatterPlot.ts'
import { computeClusterCentroids } from '../lib/snapshotPlot.ts'

const CHART_MARGIN = { top: 8, right: 8, bottom: 8, left: 8 }

/**
 * 2D scatter plot of all movies across clusters rendered on a <canvas>.
 *
 * All dot drawing and the vortex animation run imperatively via
 * requestAnimationFrame — zero React re-renders per frame, so animation
 * is always fluid regardless of point count.
 *
 * In colored (conversation) mode:
 * - Each dot's opacity reflects its argmax soft-membership probability.
 * - Exemplar dots are always drawn at a larger radius.
 * - A probability-weighted centroid cross (SVG overlay) is shown per cluster.
 * - Selecting a cluster dims other clusters; no other visual change.
 * - Clicking the chart background clears the selection.
 * - Snapshot transitions play a spiral-in / spiral-out vortex (~700 ms).
 *
 * In grey (dimmedAll) mode: uniform muted dots, no centroids, no animation.
 *
 * @param points            - Pre-computed scatter points with coords + metadata.
 * @param snapshot          - Active cluster snapshot.
 * @param selectedClusterId - Currently selected cluster UUID, or null.
 * @param onClusterClick    - Toggles or clears cluster selection.
 * @param dimmedAll         - When true, renders uniform grey dots.
 * @param baseDomain        - Fixed axis domain from the root snapshot.
 */
export function SnapshotPlot({
    points,
    snapshot,
    selectedClusterId,
    onClusterClick,
    dimmedAll = false,
    baseDomain,
}: {
    points: ScatterPoint[]
    snapshot: ClusterSnapshotDto
    selectedClusterId: string | null
    onClusterClick: (clusterId: string | null) => void
    dimmedAll?: boolean
    baseDomain?: { x: [number, number]; y: [number, number] }
}) {
    const isDark = useThemeStore((s) => s.theme === 'dark')
    const { xDomain, yDomain } = useSnapshotPlotData(points, snapshot, baseDomain)

    // ── Container size (drives canvas dimensions + centroid pixel coords) ───
    const containerRef = useRef<HTMLDivElement>(null)
    const [containerSize, setContainerSize] = useState({ width: 0, height: 0 })

    useEffect(() => {
        const el = containerRef.current
        if (!el) return
        const obs = new ResizeObserver((entries) => {
            const r = entries[0].contentRect
            setContainerSize({ width: r.width, height: r.height })
        })
        obs.observe(el)
        return () => obs.disconnect()
    }, [])

    // ── Canvas ref (handed to the imperative hook) ──────────────────────────
    const canvasRef = useRef<HTMLCanvasElement>(null)

    const { onMouseMove, onMouseLeave, onCanvasClick, hoveredPoint } = useCanvasScatterPlot({
        canvasRef,
        containerSize,
        points,
        snapshotId: snapshot.id,
        dimmedAll,
        selectedClusterId,
        isDark,
        xDomain: xDomain as [number, number],
        yDomain: yDomain as [number, number],
        margin: CHART_MARGIN,
        onClusterClick,
    })

    // ── Centroid crosses (SVG overlay, hidden during animation) ─────────────
    const centroids = useMemo(
        () => (!dimmedAll ? computeClusterCentroids(snapshot) : []),
        [snapshot, dimmedAll],
    )

    const plotW = containerSize.width - CHART_MARGIN.left - CHART_MARGIN.right
    const plotH = containerSize.height - CHART_MARGIN.top - CHART_MARGIN.bottom
    const xRange = (xDomain[1] as number) - (xDomain[0] as number)
    const yRange = (yDomain[1] as number) - (yDomain[0] as number)

    function toPixel(dx: number, dy: number) {
        return {
            px: plotW > 0 && xRange > 0
                ? CHART_MARGIN.left + ((dx - (xDomain[0] as number)) / xRange) * plotW
                : 0,
            py: plotH > 0 && yRange > 0
                ? CHART_MARGIN.top + (((yDomain[1] as number) - dy) / yRange) * plotH
                : 0,
        }
    }

    return (
        <div ref={containerRef} className="relative w-full h-full">
            {/* Dot grid background */}
            <div
                className="absolute inset-0 pointer-events-none"
                style={{
                    backgroundImage: 'radial-gradient(var(--color-border) 1px, transparent 1px)',
                    backgroundSize: '14px 14px',
                    opacity: 0.35,
                }}
            />

            {/* Main canvas — all dots and animation */}
            <canvas
                ref={canvasRef}
                style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
                onMouseMove={onMouseMove}
                onMouseLeave={onMouseLeave}
                onClick={onCanvasClick}
            />

            {/* Centroid crosses — SVG overlay aligned to plot area */}
            {!dimmedAll && centroids.length > 0 && plotW > 0 && (
                <svg
                    className="absolute inset-0 pointer-events-none"
                    width={containerSize.width}
                    height={containerSize.height}
                >
                    {centroids.map(({ clusterId, x, y }) => {
                        const { px, py } = toPixel(x, y)
                        const color = clusterColorFromUuid(clusterId, isDark)
                        const dimmed = selectedClusterId !== null && selectedClusterId !== clusterId
                        const ARM = 10
                        return (
                            <g key={clusterId} opacity={dimmed ? 0.2 : 1}>
                                <line x1={px - ARM} y1={py} x2={px + ARM} y2={py}
                                    stroke={color} strokeWidth={2.5} strokeLinecap="round" />
                                <line x1={px} y1={py - ARM} x2={px} y2={py + ARM}
                                    stroke={color} strokeWidth={2.5} strokeLinecap="round" />
                            </g>
                        )
                    })}
                </svg>
            )}

            {/* Hover tooltip */}
            {hoveredPoint && (() => {
                const { px, py } = toPixel(hoveredPoint.x, hoveredPoint.y)
                return (
                    <div
                        className="absolute pointer-events-none z-10 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-1.5 text-xs text-[var(--color-text)] shadow-md"
                        style={{ left: px + 12, top: py - 8, transform: 'translateY(-50%)' }}
                    >
                        <p className="font-medium">{hoveredPoint.title}</p>
                        {!dimmedAll && hoveredPoint.clusterLabel && (
                            <p className="text-[var(--color-muted)] mt-0.5">{hoveredPoint.clusterLabel}</p>
                        )}
                    </div>
                )
            })()}
        </div>
    )
}
