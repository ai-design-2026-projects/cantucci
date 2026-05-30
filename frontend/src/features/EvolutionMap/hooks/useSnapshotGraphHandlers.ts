import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { MouseEvent as ReactMouseEvent, WheelEvent as ReactWheelEvent } from 'react'
import { clamp } from '@/lib/utils'
import type { LayoutNode } from '../lib/radialLayout'

const MIN_ZOOM = 0.2
const MAX_ZOOM = 4
const MIN_INITIAL_SCALE = 0.6
const MAX_INITIAL_SCALE = 1.5
const DRAG_THRESHOLD = 3
const DRAG_PADDING = 40

/**
 * Owns the interactive state and event handlers for the snapshot graph.
 *
 * @param layout      - Layout nodes used to resolve hover targets.
 * @param fitScale    - Fit-to-view scale; used to compute initial zoom and reset target.
 * @param graphWidth  - Logical width of the graph content (pre-scale).
 * @param graphHeight - Logical height of the graph content (pre-scale).
 * @param width       - Container width in pixels.
 * @param height      - Container height in pixels.
 * @returns Zoom state, pan offset, hovered node, and interaction callbacks.
 */
export function useSnapshotGraphHandlers(
	layout: LayoutNode[],
	fitScale: number,
	graphWidth: number,
	graphHeight: number,
	width: number,
	height: number,
) {
	const [scale, setScale] = useState(clamp(fitScale, MIN_INITIAL_SCALE, MAX_INITIAL_SCALE))
	const [pan, setPan] = useState({ x: 0, y: 0 })
	const [hoveredId, setHoveredId] = useState<string | null>(null)
	const [isDragging, setIsDragging] = useState(false)

	const dragRef = useRef({ active: false, startX: 0, startY: 0, originX: 0, originY: 0, moved: false })
	const scaleRef = useRef(scale)

	useEffect(() => { scaleRef.current = scale }, [scale])

	useEffect(() => {
		setScale(clamp(fitScale, MIN_INITIAL_SCALE, MAX_INITIAL_SCALE))
		setPan({ x: 0, y: 0 })
	}, [fitScale])

	const hoveredNode = useMemo(() => {
		return hoveredId ? layout.find((node) => node.id === hoveredId) ?? null : null
	}, [hoveredId, layout])

	const handleWheel = useCallback((event: ReactWheelEvent<SVGSVGElement>) => {
		event.preventDefault()
		setScale((current) => {
			const next = current * (event.deltaY < 0 ? 1.1 : 0.9)
			return clamp(next, MIN_ZOOM, MAX_ZOOM)
		})
	}, [])

	const handleMouseDown = useCallback((event: ReactMouseEvent<SVGSVGElement>) => {
		dragRef.current = {
			active: true,
			startX: event.clientX,
			startY: event.clientY,
			originX: pan.x,
			originY: pan.y,
			moved: false,
		}
		setIsDragging(false)
	}, [pan.x, pan.y])

	const handleMouseMove = useCallback((event: ReactMouseEvent<SVGSVGElement>) => {
		if (!dragRef.current.active) return
		const dx = event.clientX - dragRef.current.startX
		const dy = event.clientY - dragRef.current.startY
		if (!dragRef.current.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return
		dragRef.current.moved = true
		setIsDragging(true)
		const s = scaleRef.current
		const maxPanX = (graphWidth * s + width) / 2 - DRAG_PADDING
		const maxPanY = (graphHeight * s + height) / 2 - DRAG_PADDING
		setPan({
			x: clamp(dragRef.current.originX + dx, -maxPanX, maxPanX),
			y: clamp(dragRef.current.originY + dy, -maxPanY, maxPanY),
		})
	}, [graphWidth, graphHeight, width, height])

	const handleMouseUp = useCallback(() => {
		dragRef.current.active = false
		setIsDragging(false)
	}, [])

	const handleMouseLeave = useCallback(() => {
		dragRef.current.active = false
		setIsDragging(false)
	}, [])

	const resetScale = useCallback(() => {
		setScale(clamp(fitScale, MIN_INITIAL_SCALE, MAX_INITIAL_SCALE))
		setPan({ x: 0, y: 0 })
	}, [fitScale])

	return {
		scale,
		pan,
		isDragging,
		dragRef,
		hoveredId,
		hoveredNode,
		setHoveredId,
		handleWheel,
		handleMouseDown,
		handleMouseMove,
		handleMouseUp,
		handleMouseLeave,
		resetScale,
	}
}
