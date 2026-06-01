import type { JudgeScoreDto } from '@/api/dto/eval'
import { paletteAt } from '../plots/colors'

interface JudgeScoreListProps {
    scores: JudgeScoreDto[]
}

const STAR = '★'
const EMPTY_STAR = '☆'

const ALL_DIMENSIONS = [
    'operation_appropriateness',
    'label_accuracy',
    'suggestion_meaningfulness',
    'explanation_quality',
    'intent_alignment',
    'clustering_coherence',
    'concept_axis_quality',
]

const DIMENSION_LABELS: Record<string, string> = {
    operation_appropriateness: 'Operation Appropriateness',
    label_accuracy: 'Label Accuracy',
    suggestion_meaningfulness: 'Suggestion Meaningfulness',
    explanation_quality: 'Explanation Quality',
    intent_alignment: 'Intent Alignment',
    clustering_coherence: 'Clustering Coherence',
    concept_axis_quality: 'Concept Axis Quality',
}

/**
 * All six judge dimensions are always rendered. Dimensions absent from the
 * session's scores (e.g. concept_axis_quality when no axes were built) appear
 * as "not scored" so the full judge profile is always visible.
 */
export function JudgeScoreList({ scores }: JudgeScoreListProps) {
    if (scores.length === 0 && ALL_DIMENSIONS.every((d) => !scores.find((s) => s.dimension === d))) {
        return <p className="text-xs text-[var(--color-muted)]">No judge scores yet.</p>
    }

    const byDim = Object.fromEntries(scores.map((s) => [s.dimension, s]))

    return (
        <div className="flex flex-col gap-3">
            {ALL_DIMENSIONS.map((dim, i) => {
                const s = byDim[dim]
                return (
                    <div key={dim} className="flex flex-col gap-0.5">
                        <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-medium text-[var(--color-text)]">
                                {DIMENSION_LABELS[dim] ?? dim.replace(/_/g, ' ')}
                            </span>
                            {s ? (
                                <span className="text-sm tracking-tight shrink-0" style={{ color: paletteAt(i) }}>
                                    {STAR.repeat(s.score)}{EMPTY_STAR.repeat(Math.max(0, 5 - s.score))}
                                </span>
                            ) : (
                                <span className="text-[11px] text-[var(--color-muted)] italic shrink-0">not scored</span>
                            )}
                        </div>
                        {s?.rationale && (
                            <p className="text-[11px] text-[var(--color-muted)] leading-relaxed">{s.rationale}</p>
                        )}
                        {!s && dim === 'concept_axis_quality' && (
                            <p className="text-[10px] text-[var(--color-muted)] italic">
                                No concept axes were built in this session.
                            </p>
                        )}
                        {!s && dim === 'clustering_coherence' && (
                            <p className="text-[10px] text-[var(--color-muted)] italic">
                                Scored on runs using judge v5 or later.
                            </p>
                        )}
                    </div>
                )
            })}
        </div>
    )
}
