import { useRef, useState, useEffect } from 'react'
import { useThemeStore } from '@/store/useThemeStore'
import type { ClusterSnapshotDto } from '@/api/dto/snapshots'
import type { ScatterPoint } from '../hooks/useScatterData.ts'
import { useSnapshotPlotData } from '../hooks/useSnapshotPlotData.ts'
import { useCanvasScatterPlot } from '../hooks/useCanvasScatterPlot.ts'

const CHART_MARGIN = { top: 8, right: 8, bottom: 8, left: 8 }

/**
 * 2D scatter plot of all movies across clusters rendered on a <canvas>.
 *
 * All dot drawing, centroid ring drawing, and the vortex animation run
 * imperatively via requestAnimationFrame — zero React re-renders per frame,
 * so animation is always fluid regardless of point count.
 *
 * In colored (conversation) mode:
 * - Each dot's opacity reflects its argmax soft-membership probability.
 * - Exemplar dots are always drawn at a larger radius.
 * - A probability-weighted centroid ring (circle + cross) is shown per
 *   cluster; it animates with the vortex transition.
 * - Hovering a centroid shows a cluster-label tooltip.
 * - Selecting a cluster dims other clusters; no other visual change.
 * - Clicking the chart background clears the selection.
 * - Snapshot transitions play a spiral-in / spiral-out vortex (~700 ms).
 *
 * In grey (dimmedAll) mode: uniform muted dots, no centroids, no animation.
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

    const canvasRef = useRef<HTMLCanvasElement>(null)

    const { onMouseMove, onMouseLeave, onCanvasClick, hoveredItem } = useCanvasScatterPlot({
        canvasRef,
        containerSize,
        points,
        snapshot,
        dimmedAll,
        selectedClusterId,
        isDark,
        xDomain: xDomain as [number, number],
        yDomain: yDomain as [number, number],
        margin: CHART_MARGIN,
        onClusterClick,
    })

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

            {/* Main canvas — all dots, centroid rings, and animation */}
            <canvas
                ref={canvasRef}
                style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
                onMouseMove={onMouseMove}
                onMouseLeave={onMouseLeave}
                onClick={onCanvasClick}
            />

            {/* Hover tooltip */}
            {hoveredItem && (() => {
                if (hoveredItem.kind === 'centroid') {
                    const { px, py } = toPixel(hoveredItem.x, hoveredItem.y)
                    return (
                        <div
                            className="absolute pointer-events-none z-10 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-1.5 text-xs text-[var(--color-text)] shadow-md"
                            style={{ left: px + 16, top: py - 8, transform: 'translateY(-50%)' }}
                        >
                            <p className="font-medium">{hoveredItem.label ?? 'Unlabeled'}</p>
                        </div>
                    )
                }
                const { px, py } = toPixel(hoveredItem.point.x, hoveredItem.point.y)
                return (
                    <div
                        className="absolute pointer-events-none z-10 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-1.5 text-xs text-[var(--color-text)] shadow-md"
                        style={{ left: px + 12, top: py - 8, transform: 'translateY(-50%)' }}
                    >
                        <p className="font-medium">{hoveredItem.point.title}</p>
                        {!dimmedAll && hoveredItem.point.clusterLabel && (
                            <p className="text-[var(--color-muted)] mt-0.5">{hoveredItem.point.clusterLabel}</p>
                        )}
                    </div>
                )
            })()}
        </div>
    )
}
