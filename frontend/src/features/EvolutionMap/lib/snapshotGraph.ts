import type { LayoutNode } from './radialLayout'

export const NODE_R = 32
export const LABEL_LINE_HEIGHT = 11

const OPERATION_LABELS: Record<string, string[]> = {
	unclustered:   ['unclustered'],
	base:          ['base'],
	drill_down:    ['drill down'],
	merge:         ['merge'],
	focus:         ['focus'],
	cross_filter:  ['cross', 'filter'],
	partition_by:  ['partition'],
}

/**
 * Returns display lines for a snapshot operation, split for fitting inside the node circle.
 *
 * @param operation - Snapshot operation name.
 * @returns Array of text lines to render inside the node.
 */
export function formatSnapshotOperationLines(operation: string): string[] {
	return OPERATION_LABELS[operation] ?? [operation.replace(/_/g, ' ')]
}

/**
 * Formats the small index line shown under non-base nodes.
 *
 * @param operation - Snapshot operation name.
 * @param sopIndex - Sequence number used for the node label.
 * @returns Empty string for base nodes, otherwise a numbered label.
 */
export function formatSnapshotIndexLabel(operation: string, sopIndex: number): string {
	return operation === 'base' || operation === 'unclustered' ? '' : `#${sopIndex}`
}

/**
 * Formats the tooltip heading for a graph node.
 *
 * @param node - Snapshot layout node.
 * @returns Human-readable title for the tooltip card.
 */
export function formatSnapshotTooltipTitle(node: LayoutNode): string {
	const lines = OPERATION_LABELS[node.operation] ?? [node.operation.replace(/_/g, ' ')]
	const label = lines.join(' ')
	return node.operation === 'base' || node.operation === 'unclustered' ? label : `${label} #${node.sopIndex}`
}