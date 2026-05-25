import { useCallback, useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import type { ScatterPoint } from './useScatterData.ts'
import { clusterColorFromUuid } from '@/styles/theme'

const PHASE_DURATION = 350
const TOTAL_DURATION = PHASE_DURATION * 2
const MAX_ROTATION = 4 * Math.PI
const HIT_RADIUS = 14

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

interface CanvasParams {
    canvasRef: RefObject<HTMLCanvasElement | null>
    containerSize: { width: number; height: number }
    points: ScatterPoint[]
    snapshotId: string | undefined
    dimmedAll: boolean
    selectedClusterId: string | null
    isDark: boolean
    xDomain: [number, number]
    yDomain: [number, number]
    margin: { top: number; right: number; bottom: number; left: number }
    onClusterClick: (clusterId: string | null) => void
}

/**
 * Drives all scatter-plot rendering imperatively on a <canvas> element.
 *
 * Dot positions, colors, opacities and the vortex animation are written
 * directly to the canvas context inside requestAnimationFrame callbacks —
 * zero React state updates per animation frame, so the browser can reach
 * 60 fps regardless of point count.
 *
 * The vortex fires when `snapshotId` changes while in conversation mode.
 * Visual changes (selection, theme, resize) trigger a synchronous redraw
 * only when no animation is running.
 *
 * @returns onMouseMove / onMouseLeave for tooltip, hoveredPoint for the
 *          tooltip overlay, and onCanvasClick for selection.
 */
export function useCanvasScatterPlot({
    canvasRef,
    containerSize,
    points,
    snapshotId,
    dimmedAll,
    selectedClusterId,
    isDark,
    xDomain,
    yDomain,
    margin,
    onClusterClick,
}: CanvasParams) {
    // ── Latest visual params in a ref so the draw fn always reads fresh values
    // without needing to be recreated on every render.
    const vRef = useRef({
        points, selectedClusterId, isDark, xDomain, yDomain,
        margin, containerSize, dimmedAll, onClusterClick,
    })
    vRef.current = {
        points, selectedClusterId, isDark, xDomain, yDomain,
        margin, containerSize, dimmedAll, onClusterClick,
    }

    // ── Canvas helpers ──────────────────────────────────────────────────────
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

    // Resolve --muted CSS variable once from the document root.
    function mutedColor(): string {
        return getComputedStyle(document.documentElement)
            .getPropertyValue('--muted').trim() || '#7b6d62'
    }

    // ── Core draw function — called both from React effects and from RAF ────
    // `pts` may carry an extra `_animOpacity` field during animation.
    const drawFrame = useCallback((
        pts: Array<ScatterPoint & { _animOpacity?: number }>,
    ) => {
        const canvas = canvasRef.current
        if (!canvas) return
        const ctx = canvas.getContext('2d')
        if (!ctx) return

        const { containerSize: cs, selectedClusterId: sel, isDark: dark, xDomain: xd, yDomain: yd, margin: m, dimmedAll: da } = vRef.current
        const { width: W, height: H } = cs
        if (W === 0 || H === 0) return

        // Resize canvas for device pixel ratio (resets transform, so we rescale).
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

        ctx.globalAlpha = 1
    }, [canvasRef])

    // ── Animation state — pure refs, never React state ─────────────────────
    const animRef = useRef<{
        phase: 'idle' | 'in' | 'out'
        startTime: number
        frozenPrev: ScatterPoint[]
        frozenNext: ScatterPoint[]
        rafId: number | null
        centerX: number
        centerY: number
    }>({
        phase: 'idle', startTime: 0,
        frozenPrev: [], frozenNext: [],
        rafId: null, centerX: 0, centerY: 0,
    })

    const prevSnapshotIdRef = useRef<string | undefined>(undefined)
    const isFirstMountRef = useRef(true)
    const prevPointsRef = useRef<ScatterPoint[]>([])

    const startAnimation = useCallback((
        prev: ScatterPoint[], next: ScatterPoint[], cx: number, cy: number,
    ) => {
        const anim = animRef.current
        if (anim.rafId !== null) cancelAnimationFrame(anim.rafId)
        anim.frozenPrev = prev
        anim.frozenNext = next
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
                drawFrame(transformed)
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
                drawFrame(transformed)
                anim.rafId = requestAnimationFrame(tick)
            } else {
                anim.phase = 'idle'
                anim.rafId = null
                prevPointsRef.current = vRef.current.points
                drawFrame(vRef.current.points)
            }
        }

        anim.rafId = requestAnimationFrame(tick)
    }, [drawFrame])

    // ── Effect: respond to snapshot changes (may start animation) ───────────
    useEffect(() => {
        const isFirst = isFirstMountRef.current
        isFirstMountRef.current = false

        if (snapshotId === prevSnapshotIdRef.current) return

        const prev = prevPointsRef.current
        prevSnapshotIdRef.current = snapshotId
        prevPointsRef.current = points

        const shouldAnimate = !isFirst && !dimmedAll && prev.length > 0 && points.length > 0
        if (shouldAnimate) {
            const cx = (xDomain[0] + xDomain[1]) / 2
            const cy = (yDomain[0] + yDomain[1]) / 2
            startAnimation(prev, points, cx, cy)
        } else {
            if (animRef.current.rafId !== null) {
                cancelAnimationFrame(animRef.current.rafId)
                animRef.current.rafId = null
                animRef.current.phase = 'idle'
            }
            drawFrame(points)
        }
    }, [snapshotId, dimmedAll]) // eslint-disable-line react-hooks/exhaustive-deps

    // ── Effect: redraw on visual changes when idle ──────────────────────────
    useEffect(() => {
        if (animRef.current.phase !== 'idle') return
        prevPointsRef.current = points
        drawFrame(points)
    }, [points, selectedClusterId, isDark, containerSize, xDomain, yDomain, drawFrame])

    // ── Tooltip ─────────────────────────────────────────────────────────────
    const [hoveredPoint, setHoveredPoint] = useState<ScatterPoint | null>(null)

    function findNearest(mx: number, my: number): ScatterPoint | null {
        const { points: pts, xDomain: xd, yDomain: yd, margin: m, containerSize: cs } = vRef.current
        let nearest: ScatterPoint | null = null
        let minDist = HIT_RADIUS
        for (const p of pts) {
            const { px, py } = dataToPixel(p.x, p.y, m, cs.width, cs.height, xd, yd)
            const d = Math.hypot(mx - px, my - py)
            if (d < minDist) { minDist = d; nearest = p }
        }
        return nearest
    }

    const onMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
        if (animRef.current.phase !== 'idle') { setHoveredPoint(null); return }
        const rect = (e.currentTarget as HTMLCanvasElement).getBoundingClientRect()
        setHoveredPoint(findNearest(e.clientX - rect.left, e.clientY - rect.top))
    }, []) // eslint-disable-line react-hooks/exhaustive-deps

    const onMouseLeave = useCallback(() => setHoveredPoint(null), [])

    const onCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
        if (animRef.current.phase !== 'idle') return
        const rect = (e.currentTarget as HTMLCanvasElement).getBoundingClientRect()
        const nearest = findNearest(e.clientX - rect.left, e.clientY - rect.top)
        vRef.current.onClusterClick(nearest?.clusterId ?? null)
    }, []) // eslint-disable-line react-hooks/exhaustive-deps

    return { onMouseMove, onMouseLeave, onCanvasClick, hoveredPoint }
}
