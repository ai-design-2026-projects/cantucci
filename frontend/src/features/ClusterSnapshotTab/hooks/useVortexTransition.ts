import { useEffect, useRef, useState } from 'react'
import type { ScatterPoint } from './useScatterData.ts'

export type VortexPhase = 'idle' | 'in' | 'out'

export interface VortexPoint extends ScatterPoint {
    _animOpacity: number
}

const PHASE_DURATION = 3500000
const TOTAL_DURATION = PHASE_DURATION * 2
const MAX_ROTATION = 4 * Math.PI

function easeInQuad(t: number): number {
    return t * t
}

function easeOutQuad(t: number): number {
    return t * (2 - t)
}

function rotateAround(
    px: number,
    py: number,
    cx: number,
    cy: number,
    angle: number,
): { x: number; y: number } {
    const cos = Math.cos(angle)
    const sin = Math.sin(angle)
    const dx = px - cx
    const dy = py - cy
    return {
        x: cx + dx * cos - dy * sin,
        y: cy + dx * sin + dy * cos,
    }
}

/**
 * Drives a spiral-in / spiral-out vortex transition between two ScatterPoint arrays.
 *
 * Phase 1 (0 – 350 ms): previous points spiral into `center` and fade out.
 * Phase 2 (350 – 700 ms): new points spiral out from `center` and fade in.
 *
 * Only triggers when `snapshotId` changes AND both previous and current points
 * exist. Does not animate on first mount or when the caller passes dimmedAll=true.
 *
 * @param points     - Current scatter points (from the active snapshot).
 * @param snapshotId - Active snapshot UUID (transition fires on change).
 * @param center     - Data-space center of the chart (midpoint of x/y domains).
 * @param dimmedAll  - When true, skips animation (grey silhouette mode).
 * @returns displayPoints (transformed per frame) and current phase.
 */
export function useVortexTransition(
    points: ScatterPoint[],
    snapshotId: string | undefined,
    center: { x: number; y: number },
    dimmedAll: boolean,
): { displayPoints: VortexPoint[]; phase: VortexPhase } {
    const prevSnapshotId = useRef<string | undefined>(undefined)
    const prevPoints = useRef<ScatterPoint[]>([])
    const isFirstMount = useRef(true)

    const [phase, setPhase] = useState<VortexPhase>('idle')
    const [displayPoints, setDisplayPoints] = useState<VortexPoint[]>(() =>
        points.map((p) => ({ ...p, _animOpacity: 0.85 })),
    )

    const rafRef = useRef<number | null>(null)
    const startTimeRef = useRef<number>(0)
    const frozenPrev = useRef<ScatterPoint[]>([])
    const frozenNext = useRef<ScatterPoint[]>([])

    useEffect(() => {
        if (snapshotId === prevSnapshotId.current) return

        const wasFirst = isFirstMount.current
        isFirstMount.current = false
        prevSnapshotId.current = snapshotId

        if (wasFirst || dimmedAll || prevPoints.current.length === 0 || points.length === 0) {
            prevPoints.current = points
            setDisplayPoints(points.map((p) => ({ ...p, _animOpacity: 0.85 })))
            setPhase('idle')
            return
        }

        frozenPrev.current = prevPoints.current
        frozenNext.current = points
        prevPoints.current = points

        if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)

        startTimeRef.current = performance.now()
        setPhase('in')

        function tick(now: number) {
            const elapsed = now - startTimeRef.current

            if (elapsed < PHASE_DURATION) {
                const t = easeInQuad(elapsed / PHASE_DURATION)
                const angle = -t * MAX_ROTATION
                const transformed = frozenPrev.current.map((p) => {
                    const rotated = rotateAround(
                        p.x + (center.x - p.x) * t,
                        p.y + (center.y - p.y) * t,
                        center.x,
                        center.y,
                        angle,
                    )
                    return { ...p, x: rotated.x, y: rotated.y, _animOpacity: 1 - t }
                })
                setDisplayPoints(transformed)
                rafRef.current = requestAnimationFrame(tick)
            } else if (elapsed < TOTAL_DURATION) {
                setPhase('out')
                const t = easeOutQuad((elapsed - PHASE_DURATION) / PHASE_DURATION)
                const angle = (1 - t) * MAX_ROTATION
                const transformed = frozenNext.current.map((p) => {
                    const startX = center.x + (p.x - center.x) * t
                    const startY = center.y + (p.y - center.y) * t
                    const rotated = rotateAround(startX, startY, center.x, center.y, angle)
                    return { ...p, x: rotated.x, y: rotated.y, _animOpacity: t }
                })
                setDisplayPoints(transformed)
                rafRef.current = requestAnimationFrame(tick)
            } else {
                setDisplayPoints(frozenNext.current.map((p) => ({ ...p, _animOpacity: 0.85 })))
                setPhase('idle')
                rafRef.current = null
            }
        }

        rafRef.current = requestAnimationFrame(tick)

        return () => {
            if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
        }
    }, [snapshotId, dimmedAll])

    // Keep prevPoints and displayPoints in sync when idle (not animating).
    // Guard against the race where both effects fire in the same commit when
    // snapshotId changes: frozenNext was already set by the animation effect
    // to `points`, so if they reference the same array we are mid-transition
    // and must not overwrite displayPoints.
    useEffect(() => {
        if (phase === 'idle' && points !== frozenNext.current) {
            prevPoints.current = points
            setDisplayPoints(points.map((p) => ({ ...p, _animOpacity: 0.85 })))
        }
    }, [points, phase])

    return { displayPoints, phase }
}
