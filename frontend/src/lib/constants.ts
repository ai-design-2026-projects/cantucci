/** Maps backend operation strings to human-readable node labels for the evolution map. */
export const OPERATION_LABELS: Record<string, string> = {
	base: 'Initial',
	drill_down: 'Drill Down',
	merge: 'Merge',
	recut: 'Recut',
	subcluster: 'Subcluster',
	partition_by: 'Partition',
}

/** Rotating status messages shown in the loading bubble during a turn. */
export const LOADING_MESSAGES: string[] = [
	'Analyzing your request…',
	'Searching the catalogue…',
	'Grouping similar movies…',
	'Refining the clusters…',
	'Almost there…',
]

/** Mascot expression cycle matching LOADING_MESSAGES rotation. */
export const LOADING_EXPRESSIONS = [
	'sleepy',
	'happy',
	'happy',
	'excited',
	'excited',
] as const

/** Interval between loading message rotations in ms. */
export const LOADING_ROTATE_MS = 2200

/** Maps backend step keys to human-readable loading messages. */
export const STEP_LABELS: Record<string, string> = {
    labeling: 'Naming the clusters…',
    intent: 'Understanding your request…',
    clarifier: 'Asking for clarification…',
    concept: 'Building the concept…',
    clustering: 'Re-clustering…',
    explain: 'Explaining the placement…',
    suggester: 'Looking for follow-ups…',
}

/** Maps backend step keys to mascot expressions. */
export const STEP_EXPRESSIONS: Record<string, 'happy' | 'excited' | 'sleepy'> = {
    labeling: 'happy',
    intent: 'happy',
    clarifier: 'sleepy',
    concept: 'happy',
    clustering: 'excited',
    explain: 'happy',
    suggester: 'happy',
}

/** Maximum number of exemplar IDs to display per cluster in the scatter plot. */
export const MAX_EXEMPLARS_DISPLAYED = 15

/** LocalStorage key for persisting anonymous conversation ID. */
export const ANON_CONVERSATION_KEY = 'cinepal_anon_conv_id'

/** LocalStorage key for theme preference. */
export const THEME_KEY = 'cinepal_theme'
