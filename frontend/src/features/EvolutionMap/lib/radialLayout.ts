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
}

const LEVEL_GAP = 120
const SIBLING_GAP = 140

/**
 * Compute a deterministic tree layout for a snapshot DAG.
 *
 * Root sits at (0, 0). Each level is placed on a lower row, and siblings are
 * spaced horizontally according to a stable leaf-order traversal. sopIndex is
 * a 1-based counter among siblings sharing the same operation under the same
 * parent, used for node labels.
 *
 * @param nodes - Snapshot DAG nodes.
 * @returns Array of LayoutNode with computed x, y, level, and sopIndex.
 */
export function radialLayout(nodes: ClusterSnapshotGraphNode[]): LayoutNode[] {
	if (nodes.length === 0) return []

	const childrenOf = new Map<string | null, ClusterSnapshotGraphNode[]>()
	for (const n of nodes) {
		const key = n.parent_id ?? null
		const list = childrenOf.get(key) ?? []
		list.push(n)
		childrenOf.set(key, list)
	}

	const rootCandidates = childrenOf.get(null) ?? []
	if (rootCandidates.length === 0) return []
	const root = rootCandidates[0]

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

	const rootPlacement = place(root, 0)
	const rootShift = rootPlacement.x

	return nodes
		.map((node) => {
			const placement = placements.get(node.id)
			if (!placement) {
				return {
					id: node.id,
					x: 0,
					y: 0,
					level: 0,
					operation: node.operation,
					sopIndex: 1,
					created_at: node.created_at,
					parent_id: node.parent_id,
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
				parent_id: node.parent_id,
			}
		})
}