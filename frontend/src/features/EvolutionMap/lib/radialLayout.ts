import type { ClusterSnapshotGraphNode } from '@/api/dto/snapshots'

export interface LayoutNode {
	id: string
	x: number
	y: number
	level: number
	operation: string
	sopIndex: number
	created_at: string
	parent_id: string | null
	params: Record<string, unknown>
	resolved_cluster_labels: Record<string, string>
}

export const UNCLUSTERED_NODE_ID = '__unclustered__'

const LEVEL_GAP = 120
const SIBLING_GAP = 140

const SYNTHETIC_UNCLUSTERED: ClusterSnapshotGraphNode = {
	id: UNCLUSTERED_NODE_ID,
	parent_id: null,
	operation: 'unclustered',
	created_at: '',
	params: {},
	resolved_cluster_labels: {},
}

/**
 * Compute a deterministic tree layout for a snapshot DAG.
 *
 * Always injects a synthetic "unclustered" node as the visual root. Real root
 * snapshots (parent_id === null, operation === 'base') are re-parented to it
 * for layout purposes only — the original DTOs are not mutated.
 *
 * Root sits at (0, 0). Each level is placed on a lower row, and siblings are
 * spaced horizontally according to a stable leaf-order traversal. sopIndex is
 * a 1-based counter among siblings sharing the same operation under the same
 * parent, used for node labels.
 *
 * @param nodes - Snapshot DAG nodes from the backend.
 * @returns Array of LayoutNode with computed x, y, level, and sopIndex.
 */
export function radialLayout(nodes: ClusterSnapshotGraphNode[]): LayoutNode[] {
	// Re-parent real root nodes to the synthetic unclustered node (layout only)
	const rewired = nodes.map((n) =>
		n.parent_id === null ? { ...n, parent_id: UNCLUSTERED_NODE_ID } : n
	)
	const allNodes = [SYNTHETIC_UNCLUSTERED, ...rewired]

	const childrenOf = new Map<string | null, ClusterSnapshotGraphNode[]>()
	for (const n of allNodes) {
		const key = n.parent_id ?? null
		const list = childrenOf.get(key) ?? []
		list.push(n)
		childrenOf.set(key, list)
	}

	const visited = new Set<string>()
	const placements = new Map<string, { x: number; y: number; level: number; sopIndex: number }>()
	let nextLeafX = 0

	function place(node: ClusterSnapshotGraphNode, level: number): { x: number; y: number; level: number; sopIndex: number } {
		const cached = placements.get(node.id)
		if (cached) return cached
		if (visited.has(node.id)) {
			const fallback = { x: 0, y: level * LEVEL_GAP, level, sopIndex: 1 }
			placements.set(node.id, fallback)
			return fallback
		}

		visited.add(node.id)

		const children = childrenOf.get(node.id) ?? []
		const opSeen = new Map<string, number>()
		const childPositions: { x: number; y: number; level: number; sopIndex: number }[] = []

		children.forEach((child) => {
			const seen = (opSeen.get(child.operation) ?? 0) + 1
			opSeen.set(child.operation, seen)
			const childPlacement = place(child, level + 1)
			childPositions.push({ ...childPlacement, sopIndex: seen })
		})

		let x = 0
		if (childPositions.length === 0) {
			x = nextLeafX * SIBLING_GAP
			nextLeafX += 1
		} else {
			x = childPositions.reduce((sum, child) => sum + child.x, 0) / childPositions.length
		}

		const placement = { x, y: level * LEVEL_GAP, level, sopIndex: 1 }
		placements.set(node.id, placement)

		childPositions.forEach((child, idx) => {
			const childNode = children[idx]
			placements.set(childNode.id, {
				x: child.x,
				y: child.y,
				level: child.level,
				sopIndex: child.sopIndex,
			})
		})

		return placement
	}

	const rootPlacement = place(SYNTHETIC_UNCLUSTERED, 0)
	const rootShift = rootPlacement.x

	return allNodes.map((node) => {
		const placement = placements.get(node.id)
		// The synthetic unclustered node has no parent.
		// Real root nodes (originally parent_id === null) are linked to it as their layout parent
		// so the SVG edge renderer draws the unclustered → base connection.
		const layoutParentId = node.id === UNCLUSTERED_NODE_ID
			? null
			: node.parent_id  // already rewired to UNCLUSTERED_NODE_ID for real roots

		if (!placement) {
			return {
				id: node.id,
				x: 0,
				y: 0,
				level: 0,
				operation: node.operation,
				sopIndex: 1,
				created_at: node.created_at,
				parent_id: layoutParentId,
				params: node.params,
				resolved_cluster_labels: node.resolved_cluster_labels,
			}
		}

		return {
			id: node.id,
			x: placement.x - rootShift,
			y: placement.y,
			level: placement.level,
			operation: node.operation,
			sopIndex: placement.sopIndex,
			created_at: node.created_at,
			parent_id: layoutParentId,
			params: node.params,
			resolved_cluster_labels: node.resolved_cluster_labels,
		}
	})
}
