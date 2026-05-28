import type { RunAggregateDto } from '@/api/dto/eval'
import { KpiRow } from './KpiRow'
import { DistributionsSection } from './sections/DistributionsSection'
import { PerTurnSmallMultiples } from './sections/PerTurnSmallMultiples'
import { JudgeSection } from './sections/JudgeSection'
import { SessionsTable } from './sections/SessionsTable'
import { CostSection } from './sections/CostSection'

interface SectionProps {
    title: string
    children: React.ReactNode
}

function Section({ title, children }: SectionProps) {
    return (
        <section className="flex flex-col gap-4">
            <h2 className="text-sm font-semibold text-[var(--color-text)] border-b border-[var(--color-border)] pb-2">
                {title}
            </h2>
            {children}
        </section>
    )
}

interface MainAreaProps {
    aggregates: RunAggregateDto[]
    isLoading: boolean
}

/**
 * Long-scroll main dashboard area. Sections are always rendered in the same
 * order; aggregates is length-1 for single-run and length-N for compare mode.
 */
export function MainArea({ aggregates, isLoading }: MainAreaProps) {
    if (isLoading) {
        return (
            <div className="flex-1 flex items-center justify-center">
                <div className="h-6 w-6 rounded-full border-2 border-[var(--color-primary)] border-t-transparent animate-spin" />
            </div>
        )
    }

    if (aggregates.length === 0) {
        return (
            <div className="flex-1 flex flex-col items-center justify-center gap-2 text-[var(--color-muted)]">
                <span className="text-sm">Select a run from the list to explore its results.</span>
            </div>
        )
    }

    return (
        <div className="flex-1 overflow-y-auto px-6 py-6 flex flex-col gap-10 min-h-0">
            <Section title="Overview">
                <KpiRow aggregates={aggregates} />
            </Section>

            <Section title="Metric Distributions">
                <DistributionsSection aggregates={aggregates} />
            </Section>

            <Section title="Per-turn Confidence">
                <PerTurnSmallMultiples aggregates={aggregates} />
            </Section>

            <Section title="Judge Scores">
                <JudgeSection aggregates={aggregates} />
            </Section>

            <Section title="Sessions">
                <SessionsTable aggregates={aggregates} />
            </Section>

            <Section title="Cost Analysis">
                <CostSection aggregates={aggregates} />
            </Section>
        </div>
    )
}
