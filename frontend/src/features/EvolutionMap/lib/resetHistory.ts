import { deleteSnapshotFetcher } from '@/api/services/snapshots'
import type { LayoutNode } from './radialLayout'

/**
 * Delete every non-base snapshot in the evolution tree, leaves first.
 * Iterates until no non-base nodes remain, picking deletion-ready nodes
 * (those whose children are already deleted) each pass.
 *
 * @param nodes - Full layout node array for the conversation.
 * @throws Re-throws any network error from deleteSnapshotFetcher.
 */
export async function resetHistory(nodes: LayoutNode[]): Promise<void> {
    const nonBase = nodes.filter((n) => n.operation !== 'base')
    if (nonBase.length === 0) return

    const childrenOf = new Map<string, string[]>()
    for (const n of nonBase) {
        if (n.parent_id) {
            const list = childrenOf.get(n.parent_id) ?? []
            list.push(n.id)
            childrenOf.set(n.parent_id, list)
        }
    }

    const remaining = new Set(nonBase.map((n) => n.id))

    while (remaining.size > 0) {
        const leaves = [...remaining].filter((id) => {
            const children = childrenOf.get(id) ?? []
            return children.every((c) => !remaining.has(c))
        })
        if (leaves.length === 0) throw new Error('Cycle detected in snapshot graph — cannot reset')
        for (const id of leaves) {
            await deleteSnapshotFetcher(id)
            remaining.delete(id)
        }
    }
}
