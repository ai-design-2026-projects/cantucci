import type { JudgeScoreDto } from '@/api/dto/eval'
import { paletteAt } from '../plots/colors'

interface JudgeScoreListProps {
    scores: JudgeScoreDto[]
}

const STAR = '★'
const EMPTY_STAR = '☆'

/**
 * List of 5 judge dimension scores with star rating and rationale text.
 */
export function JudgeScoreList({ scores }: JudgeScoreListProps) {
    if (scores.length === 0) {
        return <p className="text-xs text-[var(--color-muted)]">No judge scores yet.</p>
    }

    return (
        <div className="flex flex-col gap-3">
            {scores.map((s, i) => (
                <div key={s.dimension} className="flex flex-col gap-0.5">
                    <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-[var(--color-text)]">
                            {s.dimension.replace(/_/g, ' ')}
                        </span>
                        <span className="text-sm tracking-tight" style={{ color: paletteAt(i) }}>
                            {STAR.repeat(s.score)}{EMPTY_STAR.repeat(5 - s.score)}
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
