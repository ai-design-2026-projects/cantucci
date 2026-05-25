import { useCallback, useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import type { ScatterPoint } from './useScatterData.ts'
import type { ClusterSnapshotDto } from '@/api/dto/snapshots'
import { clusterColorFromUuid } from '@/styles/theme'

const PHASE_DURATION = 350
const TOTAL_DURATION = PHASE_DURATION * 2
const MAX_ROTATION = 4 * Math.PI
const HIT_RADIUS = 14
const CENTROID_HIT_RADIUS = 16
const CENTROID_RING_R = 12
const CENTROID_ARM = 6

function easeInQuad(t: number): number { return t * t }
function easeOutQuad(t: number): number { return t * (2 - t) }

function rotateAround(
    px: number, py: number,
    cx: number, cy: number,
    angle: number,
): { x: number; y: number } {
    const cos = Math.cos(angle)
    const sin = Math.sin(angle)
    return {
        x: cx + (px - cx) * cos - (py - cy) * sin,
        y: cy + (px - cx) * sin + (py - cy) * cos,
    }
}

interface CentroidData {
    clusterId: string
    label: string | null
    x: number
    y: number
}

type AnimCentroid = CentroidData & { _animOpacity?: number }

export type HoveredItem =
    | { kind: 'point'; point: ScatterPoint }
    | { kind: 'centroid'; clusterId: string; label: string | null; x: number; y: number }

interface CanvasParams {
    canvasRef: RefObject<HTMLCanvasElement | null>
    containerSize: { width: number; height: number }
    points: ScatterPoint[]
    snapshot: ClusterSnapshotDto
    dimmedAll: boolean
    selectedClusterId: string | null
    isDark: boolean
    xDomain: [number, number]
    yDomain: [number, number]
    margin: { top: number; right: number; bottom: number; left: number }
    onClusterClick: (clusterId: string | null) => void
}

function computeCentroidsFromSnapshot(snapshot: ClusterSnapshotDto): CentroidData[] {
    const result: CentroidData[] = []
    for (const cluster of snapshot.clusters) {
        let sumW = 0, sumX = 0, sumY = 0
        for (const m of snapshot.members) {
            if (m.cluster_id !== cluster.id) continue
            sumW += m.probability
            sumX += m.probability * m.umap_x
            sumY += m.probability * m.umap_y
        }
        if (sumW === 0) continue
        result.push({ clusterId: cluster.id, label: cluster.label, x: sumX / sumW, y: sumY / sumW })
    }
    return result
}

/**
 * Drives all scatter-plot rendering imperatively on a <canvas> element.
 *
 * Dots and centroid rings are drawn directly via the 2D canvas API inside
 * requestAnimationFrame callbacks — zero React state updates per animation
 * frame, so the browser reaches 60 fps regardless of point count.
 *
 * Centroids animate with the vortex (phase 1: spiral in; phase 2: spiral out).
 * Hovering a centroid ring returns a `{ kind: 'centroid' }` item used to
 * render a cluster-label tooltip in the parent.
 */
export function useCanvasScatterPlot({
    canvasRef,
    containerSize,
    points,
    snapshot,
    dimmedAll,
    selectedClusterId,
    isDark,
    xDomain,
    yDomain,
    margin,
    onClusterClick,
}: CanvasParams) {
    const centroids = computeCentroidsFromSnapshot(snapshot)

    const vRef = useRef({
        points, selectedClusterId, isDark, xDomain, yDomain,
        margin, containerSize, dimmedAll, onClusterClick, centroids,
    })
    vRef.current = {
        points, selectedClusterId, isDark, xDomain, yDomain,
        margin, containerSize, dimmedAll, onClusterClick, centroids,
    }

    function dataToPixel(
        x: number, y: number,
        m: typeof margin, W: number, H: number,
        xd: [number, number], yd: [number, number],
    ) {
        const plotW = W - m.left - m.right
        const plotH = H - m.top - m.bottom
        return {
            px: m.left + ((x - xd[0]) / (xd[1] - xd[0])) * plotW,
            py: m.top + ((yd[1] - y) / (yd[1] - yd[0])) * plotH,
        }
    }

    function mutedColor(): string {
        return getComputedStyle(document.documentElement)
            .getPropertyValue('--muted').trim() || '#7b6d62'
    }

    const drawFrame = useCallback((
        pts: Array<ScatterPoint & { _animOpacity?: number }>,
        animCentroids?: AnimCentroid[],
    ) => {
        const canvas = canvasRef.current
        if (!canvas) return
        const ctx = canvas.getContext('2d')
        if (!ctx) return

        const { containerSize: cs, selectedClusterId: sel, isDark: dark, xDomain: xd, yDomain: yd, margin: m, dimmedAll: da, centroids: currentCentroids } = vRef.current
        const { width: W, height: H } = cs
        if (W === 0 || H === 0) return

        const dpr = window.devicePixelRatio || 1
        const physW = Math.round(W * dpr)
        const physH = Math.round(H * dpr)
        if (canvas.width !== physW || canvas.height !== physH) {
            canvas.width = physW
            canvas.height = physH
        }
        ctx.resetTransform()
        ctx.scale(dpr, dpr)
        ctx.clearRect(0, 0, W, H)

        const muted = mutedColor()

        for (const p of pts) {
            if (xd[1] === xd[0] || yd[1] === yd[0]) continue
            const { px, py } = dataToPixel(p.x, p.y, m, W, H, xd, yd)
            const color = da ? muted : (p.clusterId ? clusterColorFromUuid(p.clusterId, dark) : muted)
            const dimmed = !da && sel !== null && p.clusterId !== sel

            let opacity: number
            if (p._animOpacity !== undefined) {
                opacity = p._animOpacity
            } else if (da) {
                opacity = 0.4
            } else if (dimmed) {
                opacity = 0.15
            } else {
                opacity = Math.min(1, 0.25 + 0.75 * (p.probability ?? 0.7))
            }

            const r = (!da && p.isExemplar) ? 9 : (da ? 4 : 5)

            ctx.globalAlpha = opacity
            ctx.fillStyle = color
            ctx.beginPath()
            ctx.arc(px, py, r, 0, Math.PI * 2)
            ctx.fill()
        }

        if (!da) {
            const centsToRender: AnimCentroid[] = animCentroids ?? currentCentroids
            ctx.lineCap = 'round'
            for (const c of centsToRender) {
                if (xd[1] === xd[0] || yd[1] === yd[0]) continue
                const { px, py } = dataToPixel(c.x, c.y, m, W, H, xd, yd)
                const color = clusterColorFromUuid(c.clusterId, dark)
                const dimmed = sel !== null && c.clusterId !== sel
                const opacity = c._animOpacity !== undefined
                    ? c._animOpacity
                    : (dimmed ? 0.2 : 1.0)

                ctx.globalAlpha = opacity

                // halo pass — thick dark ring drawn first, sits underneath the color
                ctx.strokeStyle = 'rgba(0,0,0,0.45)'
                ctx.lineWidth = 4.5
                ctx.beginPath()
                ctx.arc(px, py, CENTROID_RING_R, 0, Math.PI * 2)
                ctx.stroke()

                // color pass — thinner ring on top
                ctx.strokeStyle = color
                ctx.lineWidth = 2
                ctx.beginPath()
                ctx.arc(px, py, CENTROID_RING_R, 0, Math.PI * 2)
                ctx.stroke()

                // inner cross — halo then color
                ctx.strokeStyle = 'rgba(0,0,0,0.45)'
                ctx.lineWidth = 4.5
                ctx.beginPath()
                ctx.moveTo(px - CENTROID_ARM, py)
                ctx.lineTo(px + CENTROID_ARM, py)
                ctx.moveTo(px, py - CENTROID_ARM)
                ctx.lineTo(px, py + CENTROID_ARM)
                ctx.stroke()

                ctx.strokeStyle = color
                ctx.lineWidth = 2
                ctx.beginPath()
                ctx.moveTo(px - CENTROID_ARM, py)
                ctx.lineTo(px + CENTROID_ARM, py)
                ctx.moveTo(px, py - CENTROID_ARM)
                ctx.lineTo(px, py + CENTROID_ARM)
                ctx.stroke()
            }
        }

        ctx.globalAlpha = 1
    }, [canvasRef])

    const animRef = useRef<{
        phase: 'idle' | 'in' | 'out'
        startTime: number
        frozenPrev: ScatterPoint[]
        frozenNext: ScatterPoint[]
        frozenPrevCentroids: CentroidData[]
        frozenNextCentroids: CentroidData[]
        rafId: number | null
        centerX: number
        centerY: number
    }>({
        phase: 'idle', startTime: 0,
        frozenPrev: [], frozenNext: [],
        frozenPrevCentroids: [], frozenNextCentroids: [],
        rafId: null, centerX: 0, centerY: 0,
    })

    const prevSnapshotIdRef = useRef<string | undefined>(undefined)
    const prevDimmedAllRef = useRef(dimmedAll)
    const isFirstMountRef = useRef(true)
    const prevPointsRef = useRef<ScatterPoint[]>([])
    const prevCentroidsRef = useRef<CentroidData[]>([])

    const startAnimation = useCallback((
        prev: ScatterPoint[], next: ScatterPoint[],
        prevCentroids: CentroidData[], nextCentroids: CentroidData[],
        cx: number, cy: number,
    ) => {
        const anim = animRef.current
        if (anim.rafId !== null) cancelAnimationFrame(anim.rafId)
        anim.frozenPrev = prev
        anim.frozenNext = next
        anim.frozenPrevCentroids = prevCentroids
        anim.frozenNextCentroids = nextCentroids
        anim.centerX = cx
        anim.centerY = cy
        anim.startTime = performance.now()
        anim.phase = 'in'

        function tick(now: number) {
            const elapsed = now - anim.startTime
            const { centerX: ccx, centerY: ccy } = anim

            if (elapsed < PHASE_DURATION) {
                const t = easeInQuad(elapsed / PHASE_DURATION)
                const angle = -t * MAX_ROTATION
                const transformed = anim.frozenPrev.map((p) => {
                    const ix = p.x + (ccx - p.x) * t
                    const iy = p.y + (ccy - p.y) * t
                    const rot = rotateAround(ix, iy, ccx, ccy, angle)
                    return { ...p, x: rot.x, y: rot.y, _animOpacity: 1 - t }
                })
                const transformedCentroids = anim.frozenPrevCentroids.map((c) => {
                    const ix = c.x + (ccx - c.x) * t
                    const iy = c.y + (ccy - c.y) * t
                    const rot = rotateAround(ix, iy, ccx, ccy, angle)
                    return { ...c, x: rot.x, y: rot.y, _animOpacity: 1 - t }
                })
                drawFrame(transformed, transformedCentroids)
                anim.rafId = requestAnimationFrame(tick)
            } else if (elapsed < TOTAL_DURATION) {
                anim.phase = 'out'
                const t = easeOutQuad((elapsed - PHASE_DURATION) / PHASE_DURATION)
                const angle = (1 - t) * MAX_ROTATION
                const transformed = anim.frozenNext.map((p) => {
                    const sx = ccx + (p.x - ccx) * t
                    const sy = ccy + (p.y - ccy) * t
                    const rot = rotateAround(sx, sy, ccx, ccy, angle)
                    return { ...p, x: rot.x, y: rot.y, _animOpacity: t }
                })
                const transformedCentroids = anim.frozenNextCentroids.map((c) => {
                    const sx = ccx + (c.x - ccx) * t
                    const sy = ccy + (c.y - ccy) * t
                    const rot = rotateAround(sx, sy, ccx, ccy, angle)
                    return { ...c, x: rot.x, y: rot.y, _animOpacity: t }
                })
                drawFrame(transformed, transformedCentroids)
                anim.rafId = requestAnimationFrame(tick)
            } else {
                anim.phase = 'idle'
                anim.rafId = null
                prevPointsRef.current = vRef.current.points
                prevCentroidsRef.current = vRef.current.centroids
                drawFrame(vRef.current.points)
            }
        }

        anim.rafId = requestAnimationFrame(tick)
    }, [drawFrame])

    useEffect(() => {
        const isFirst = isFirstMountRef.current
        isFirstMountRef.current = false

        const dimmedChanged = dimmedAll !== prevDimmedAllRef.current
        prevDimmedAllRef.current = dimmedAll

        if (snapshot.id === prevSnapshotIdRef.current && !dimmedChanged) return

        const prev = prevPointsRef.current
        const prevCentroids = prevCentroidsRef.current
        prevSnapshotIdRef.current = snapshot.id
        prevPointsRef.current = points
        prevCentroidsRef.current = vRef.current.centroids

        // Animate when entering colored mode (unclustered → base) or switching between snapshots.
        // Skip when entering dimmed mode (base → unclustered) so grey renders immediately.
        const shouldAnimate = !isFirst && !dimmedAll && prev.length > 0 && points.length > 0
        if (shouldAnimate) {
            const cx = (xDomain[0] + xDomain[1]) / 2
            const cy = (yDomain[0] + yDomain[1]) / 2
            startAnimation(prev, points, prevCentroids, vRef.current.centroids, cx, cy)
        } else {
            if (animRef.current.rafId !== null) {
                cancelAnimationFrame(animRef.current.rafId)
                animRef.current.rafId = null
                animRef.current.phase = 'idle'
            }
            drawFrame(points)
        }
    }, [snapshot.id, dimmedAll]) // eslint-disable-line react-hooks/exhaustive-deps

    useEffect(() => {
        if (animRef.current.phase !== 'idle') return
        prevPointsRef.current = points
        prevCentroidsRef.current = vRef.current.centroids
        drawFrame(points)
    }, [points, selectedClusterId, isDark, containerSize, xDomain, yDomain, drawFrame])

    const [hoveredItem, setHoveredItem] = useState<HoveredItem | null>(null)

    function findNearest(mx: number, my: number): HoveredItem | null {
        const { points: pts, xDomain: xd, yDomain: yd, margin: m, containerSize: cs, centroids: cents } = vRef.current
        let nearest: HoveredItem | null = null
        let minDist = HIT_RADIUS
        for (const p of pts) {
            const { px, py } = dataToPixel(p.x, p.y, m, cs.width, cs.height, xd, yd)
            const d = Math.hypot(mx - px, my - py)
            if (d < minDist) { minDist = d; nearest = { kind: 'point', point: p } }
        }
        for (const c of cents) {
            const { px, py } = dataToPixel(c.x, c.y, m, cs.width, cs.height, xd, yd)
            const d = Math.hypot(mx - px, my - py)
            if (d < CENTROID_HIT_RADIUS && d < minDist) {
                minDist = d
                nearest = { kind: 'centroid', clusterId: c.clusterId, label: c.label, x: c.x, y: c.y }
            }
        }
        return nearest
    }

    const onMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
        if (animRef.current.phase !== 'idle') { setHoveredItem(null); return }
        const rect = (e.currentTarget as HTMLCanvasElement).getBoundingClientRect()
        setHoveredItem(findNearest(e.clientX - rect.left, e.clientY - rect.top))
    }, []) // eslint-disable-line react-hooks/exhaustive-deps

    const onMouseLeave = useCallback(() => setHoveredItem(null), [])

    const onCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
        if (animRef.current.phase !== 'idle') return
        const rect = (e.currentTarget as HTMLCanvasElement).getBoundingClientRect()
        const item = findNearest(e.clientX - rect.left, e.clientY - rect.top)
        if (item?.kind === 'centroid') {
            vRef.current.onClusterClick(item.clusterId)
        } else if (item?.kind === 'point') {
            vRef.current.onClusterClick(item.point.clusterId ?? null)
        } else {
            vRef.current.onClusterClick(null)
        }
    }, []) // eslint-disable-line react-hooks/exhaustive-deps

    return { onMouseMove, onMouseLeave, onCanvasClick, hoveredItem }
}
