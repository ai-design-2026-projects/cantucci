import type { LayoutNode } from './radialLayout'

export const NODE_R = 32
export const LABEL_LINE_HEIGHT = 11

/**
 * Formats a snapshot operation for the in-node label.
 *
 * @param operation - Snapshot operation name.
 * @returns Human-readable label for the graph node.
 */
export function formatSnapshotOperationLabel(operation: LayoutNode['operation']): string {
	return operation === 'base' ? 'base' : operation.replace('_', ' ')
}

/**
 * Formats the small index line shown under non-base nodes.
 *
 * @param operation - Snapshot operation name.
 * @param sopIndex - Sequence number used for the node label.
 * @returns Empty string for base nodes, otherwise a numbered label.
 */
export function formatSnapshotIndexLabel(operation: LayoutNode['operation'], sopIndex: number): string {
	return operation === 'base' ? '' : `#${sopIndex}`
}

/**
 * Formats the tooltip heading for a graph node.
 *
 * @param node - Snapshot layout node.
 * @returns Human-readable title for the tooltip card.
 */
export function formatSnapshotTooltipTitle(node: LayoutNode): string {
	return node.operation === 'base' ? 'Base snapshot' : `${node.operation.replace('_', ' ')} #${node.sopIndex}`
}