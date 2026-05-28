import type { LayoutNode } from './radialLayout'

export const NODE_R = 32
export const LABEL_LINE_HEIGHT = 11

const MAX_LINE = 11

function trunc(s: string, max = MAX_LINE): string {
	return s.length > max ? s.slice(0, max - 1) + '…' : s
}

function circleLines(node: LayoutNode): string[] {
	const { operation, params, resolved_cluster_labels } = node
	switch (operation) {
		case 'base':
			return ['Base']
		case 'unclustered':
			return ['Unclustered']
		case 'drill_down': {
			const concept = typeof params.concept === 'string' ? params.concept : ''
			return ['Drill down', trunc(concept)]
		}
		case 'merge': {
			const labels = Object.values(resolved_cluster_labels)
			if (labels.length === 0) return ['Merge']
			const shorts = labels.slice(0, 2).map((l) => trunc(l.split(' ')[0], 5))
			return ['Merge', shorts.join(' + ') + (labels.length > 2 ? ` +${labels.length - 2}` : '')]
		}
		case 'focus': {
			const label = Object.values(resolved_cluster_labels)[0] ?? ''
			return ['Focus', trunc(label)]
		}
		case 'cross_filter': {
			const parts: string[] = []
			if (Array.isArray(params.genres) && params.genres.length > 0)
				parts.push((params.genres as string[]).slice(0, 2).join(', '))
			if (typeof params.release_year_min === 'number' && typeof params.release_year_max === 'number')
				parts.push(`${params.release_year_min}–${params.release_year_max}`)
			else if (typeof params.release_year_min === 'number')
				parts.push(`≥${params.release_year_min}`)
			else if (typeof params.release_year_max === 'number')
				parts.push(`≤${params.release_year_max}`)
			if (typeof params.director === 'string') parts.push(params.director)
			if (parts.length === 0) return ['Filter']
			return ['Filter', trunc(parts.slice(0, 2).join(', '))]
		}
		case 'exclude': {
			const label = Object.values(resolved_cluster_labels)[0] ?? ''
			return ['Exclude', trunc(label)]
		}
		case 'partition_by': {
			const attr = typeof params.attribute === 'string' ? params.attribute.replace(/_/g, ' ') : ''
			return ['By', trunc(attr)]
		}
		default:
			return [operation.replace(/_/g, ' ')]
	}
}

function tooltipTitle(node: LayoutNode): string {
	const { operation, params, resolved_cluster_labels } = node
	switch (operation) {
		case 'base':
		case 'unclustered':
			return operation
		case 'drill_down': {
			const concept = typeof params.concept === 'string' ? params.concept : ''
			return `Drill down ${concept}`
		}
		case 'merge': {
			const labels = Object.values(resolved_cluster_labels)
			if (labels.length === 0) return 'Merge'
			return `Merge: ${labels.join(' + ')}`
		}
		case 'focus': {
			const label = Object.values(resolved_cluster_labels)[0] ?? ''
			return `Focus: ${label}`
		}
		case 'cross_filter': {
			const parts: string[] = []
			if (Array.isArray(params.genres) && params.genres.length > 0)
				parts.push((params.genres as string[]).join(', '))
			if (typeof params.release_year_min === 'number' && typeof params.release_year_max === 'number')
				parts.push(`${params.release_year_min}–${params.release_year_max}`)
			else if (typeof params.release_year_min === 'number')
				parts.push(`≥${params.release_year_min}`)
			else if (typeof params.release_year_max === 'number')
				parts.push(`≤${params.release_year_max}`)
			if (typeof params.director === 'string') parts.push(params.director)
			return `Filter: ${parts.join(', ')}`
		}
		case 'exclude': {
			const label = Object.values(resolved_cluster_labels)[0] ?? '—'
			return `Excluded: ${label}`
		}
		case 'partition_by': {
			const attr = typeof params.attribute === 'string' ? params.attribute.replace(/_/g, ' ') : ''
			const bins = Array.isArray(params.bins) ? (params.bins as Array<{ label: string }>).map((b) => b.label) : []
			const binStr = bins.length > 0 ? ` (${bins.join(', ')})` : ''
			return `By: ${attr}${binStr}`
		}
		default:
			return operation.replace(/_/g, ' ')
	}
}

/**
 * Returns display lines for a snapshot node, split for fitting inside the node circle.
 *
 * @param node - Snapshot layout node.
 * @returns Array of text lines to render inside the node.
 */
export function formatSnapshotOperationLines(node: LayoutNode): string[] {
	return circleLines(node)
}

/**
 * Always returns an empty string — the sequential index suffix is no longer shown.
 *
 * @param _operation - Unused.
 * @param _sopIndex  - Unused.
 * @returns Empty string.
 */
export function formatSnapshotIndexLabel(_operation: string, _sopIndex: number): string {
	return ''
}

/**
 * Formats the tooltip heading for a graph node.
 *
 * @param node - Snapshot layout node.
 * @returns Human-readable title for the tooltip card.
 */
export function formatSnapshotTooltipTitle(node: LayoutNode): string {
	return tooltipTitle(node)
}
