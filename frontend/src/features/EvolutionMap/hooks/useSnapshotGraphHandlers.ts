import { useCallback, useEffect, useMemo, useState } from 'react'
import type { WheelEvent as ReactWheelEvent } from 'react'
import { clamp } from '@/lib/utils'
import type { LayoutNode } from '../lib/radialLayout'

/**
 * Owns the interactive state and event handlers for the snapshot graph.
 *
 * @param layout - Layout nodes used to resolve hover targets.
 * @param fitScale - Maximum zoom level used to cap wheel scaling.
 * @returns Zoom state, hovered node, and interaction callbacks.
 */
export function useSnapshotGraphHandlers(layout: LayoutNode[], fitScale: number) {
	const [scale, setScale] = useState(1)
	const [hoveredId, setHoveredId] = useState<string | null>(null)

	useEffect(() => {
		setScale(fitScale)
	}, [fitScale])

	const hoveredNode = useMemo(() => {
		return hoveredId ? layout.find((node) => node.id === hoveredId) ?? null : null
	}, [hoveredId, layout])

	const handleWheel = useCallback((event: ReactWheelEvent<SVGSVGElement>) => {
		event.preventDefault()
		setScale((current) => {
			const next = current * (event.deltaY < 0 ? 1.1 : 0.9)
			return clamp(next, 0.05, fitScale)
		})
	}, [fitScale])

	const resetScale = useCallback(() => {
		setScale(fitScale)
	}, [fitScale])

	return {
		scale,
		hoveredId,
		hoveredNode,
		setHoveredId,
		handleWheel,
		resetScale,
	}
}