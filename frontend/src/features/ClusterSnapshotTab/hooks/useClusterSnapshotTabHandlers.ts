import { useState } from 'react'

/**
 * Owns the tab-local UI state for the snapshot tab.
 *
 * @returns Popup and modal open state plus callbacks for toggling them.
 */
export function useClusterSnapshotTabHandlers() {
	const [selectedMovieId, setSelectedMovieId] = useState<number | null>(null)
	const [evolutionOpen, setEvolutionOpen] = useState(false)
	const [inspectOpen, setInspectOpen] = useState(false)

	return {
		selectedMovieId,
		setSelectedMovieId,
		evolutionOpen,
		setEvolutionOpen,
		inspectOpen,
		setInspectOpen,
	}
}