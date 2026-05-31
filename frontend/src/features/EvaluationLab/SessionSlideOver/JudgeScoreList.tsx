import type { JudgeScoreDto } from '@/api/dto/eval'
import { paletteAt } from '../plots/colors'

interface JudgeScoreListProps {
    scores: JudgeScoreDto[]
}

const STAR = '★'
const EMPTY_STAR = '☆'

const DIMENSION_LABELS: Record<string, string> = {
    operation_appropriateness: 'Operation Appropriateness',
    label_accuracy: 'Label Accuracy',
    suggestion_meaningfulness: 'Suggestion Meaningfulness',
    explanation_quality: 'Explanation Quality',
    intent_alignment: 'Intent Alignment',
    concept_axis_quality: 'Concept Axis Quality',
}

/**
 * List of judge dimension scores with a human-readable label, star rating,
 * and rationale text.
 */
export function JudgeScoreList({ scores }: JudgeScoreListProps) {
    if (scores.length === 0) {
        return <p className="text-xs text-[var(--color-muted)]">No judge scores yet.</p>
    }

    return (
        <div className="flex flex-col gap-3">
            {scores.map((s, i) => (
                <div key={s.dimension} className="flex flex-col gap-0.5">
                    <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-medium text-[var(--color-text)]">
                            {DIMENSION_LABELS[s.dimension] ?? s.dimension.replace(/_/g, ' ')}
                        </span>
                        <span className="text-sm tracking-tight shrink-0" style={{ color: paletteAt(i) }}>
                            {STAR.repeat(s.score)}{EMPTY_STAR.repeat(Math.max(0, 5 - s.score))}
                        </span>
                    </div>
                    {s.rationale && (
                        <p className="text-[11px] text-[var(--color-muted)] leading-relaxed">{s.rationale}</p>
                    )}
                </div>
            ))}
        </div>
    )
}
