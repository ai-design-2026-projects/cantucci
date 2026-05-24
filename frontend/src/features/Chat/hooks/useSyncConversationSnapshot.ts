import { useEffect } from 'react'
import { useSnapshotStore } from '@/store/useSnapshotStore'

/**
 * Syncs the active snapshot store with the conversation's current snapshot ID.
 * Runs whenever the conversation's current_cluster_snapshot_id changes.
 *
 * @param currentClusterSnapshotId - The snapshot the conversation currently points to.
 */
export function useSyncConversationSnapshot(
	currentClusterSnapshotId: string | null | undefined,
) {
	const setActiveSnapshotId = useSnapshotStore((s) => s.setActiveSnapshotId)
	const activeSnapshotId = useSnapshotStore((s) => s.activeSnapshotId)

	useEffect(() => {
		if (currentClusterSnapshotId && currentClusterSnapshotId !== activeSnapshotId) {
			setActiveSnapshotId(currentClusterSnapshotId)
		}
	}, [currentClusterSnapshotId, activeSnapshotId, setActiveSnapshotId])
}
