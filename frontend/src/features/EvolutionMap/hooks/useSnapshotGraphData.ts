import { useMemo } from 'react'
import type { LayoutNode } from '../lib/radialLayout'
import { LABEL_LINE_HEIGHT, NODE_R } from '../lib/snapshotGraph.ts'

/**
 * Derives graph bounds and fit-to-view transform for the snapshot graph.
 *
 * @param layout - Layout nodes to render.
 * @param width - Available graph width.
 * @param height - Available graph height.
 * @returns Bounds, fit scale, and translation data for the SVG viewport.
 */
export function useSnapshotGraphData(layout: LayoutNode[], width: number, height: number) {
	const bounds = useMemo(() => {
		if (layout.length === 0) {
			return { minX: 0, maxX: 1, minY: 0, maxY: 1 }
		}

		const labelPadding = NODE_R + 8
		const xs = layout.map((node) => node.x)
		const ys = layout.map((node) => node.y)

		return {
			minX: Math.min(...xs) - labelPadding,
			maxX: Math.max(...xs) + labelPadding,
			minY: Math.min(...ys) - NODE_R - 4,
			maxY: Math.max(...ys) + NODE_R + LABEL_LINE_HEIGHT + 4,
		}
	}, [layout])

	const graphWidth = Math.max(bounds.maxX - bounds.minX, 1)
	const graphHeight = Math.max(bounds.maxY - bounds.minY, 1)
	const fitScale = Math.min(width / graphWidth, height / graphHeight)

	const transform = useMemo(() => {
		const x = (width - graphWidth * fitScale) / 2 - bounds.minX * fitScale
		const y = (height - graphHeight * fitScale) / 2 - bounds.minY * fitScale
		return { x, y }
	}, [bounds.minX, bounds.minY, fitScale, graphHeight, graphWidth, height, width])

	return {
		bounds,
		graphWidth,
		graphHeight,
		fitScale,
		transform,
	}
}