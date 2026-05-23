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

const RING_RADIUS = 120

/**
 * Compute a deterministic radial layout for a snapshot DAG.
 *
 * Root sits at (0, 0). Each BFS level is placed on a ring of radius
 * level * RING_RADIUS. Siblings are spaced uniformly within their
 * parent's angular sector. sopIndex is a 1-based counter among siblings
 * sharing the same operation under the same parent, used for node labels.
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

  const result: LayoutNode[] = []

  function place(
    node: ClusterSnapshotGraphNode,
    level: number,
    angleStart: number,
    angleSector: number,
    siblingIndex: number,
    totalSiblings: number,
    sopIndex: number,
  ) {
    let x = 0
    let y = 0
    if (level === 0) {
      x = 0
      y = 0
    } else {
      const midAngle = angleStart + (siblingIndex + 0.5) * (angleSector / totalSiblings)
      const r = level * RING_RADIUS
      x = Math.cos(midAngle) * r
      y = Math.sin(midAngle) * r
    }

    result.push({
      id: node.id,
      x,
      y,
      level,
      operation: node.operation,
      sopIndex,
      created_at: node.created_at,
      parent_id: node.parent_id,
    })

    const children = childrenOf.get(node.id) ?? []
    if (children.length === 0) return

    const childSector = level === 0 ? 2 * Math.PI : angleSector / totalSiblings
    const childAngleStart = level === 0 ? 0 : angleStart + siblingIndex * (angleSector / totalSiblings)

    const opCount = new Map<string, number>()
    children.forEach((c) => {
      opCount.set(c.operation, (opCount.get(c.operation) ?? 0) + 1)
    })
    const opSeen = new Map<string, number>()

    children.forEach((child, idx) => {
      const seen = (opSeen.get(child.operation) ?? 0) + 1
      opSeen.set(child.operation, seen)
      place(child, level + 1, childAngleStart, childSector, idx, children.length, seen)
    })
  }

  place(root, 0, 0, 2 * Math.PI, 0, 1, 1)
  return result
}
