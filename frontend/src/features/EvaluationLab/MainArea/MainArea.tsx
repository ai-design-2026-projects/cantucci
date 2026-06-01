import type { ReactNode } from 'react'
import type { RunAggregateDto } from '@/api/dto/eval'
import { KpiRow } from './KpiRow'
import { DistributionsSection } from './sections/DistributionsSection'
import { JudgeSection } from './sections/JudgeSection'
import { PersonaStatsSection } from './sections/PersonaStatsSection'
import { CostSection } from './sections/CostSection'
import { SessionsTable } from './sections/SessionsTable'

interface SectionProps {
    title: string
    description?: string
    children: ReactNode
}

function Section({ title, description, children }: SectionProps) {
    return (
        <section className="flex flex-col gap-4">
            <div className="border-b border-[var(--color-border)] pb-2">
                <h2 className="text-sm font-semibold text-[var(--color-text)]">{title}</h2>
                {description && (
                    <p className="text-xs text-[var(--color-muted)] mt-0.5">{description}</p>
                )}
            </div>
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
        <div className="flex-1 overflow-y-auto scrollbar-styled px-6 py-6 flex flex-col gap-10 min-h-0">
            <Section title="Overview">
                <KpiRow aggregates={aggregates} />
            </Section>

            <Section
                title="Metric Distributions"
                description="Deterministic metrics computed from session data. In single-run view, each metric card shows mean value with 95% confidence interval and a per-session spread strip. In compare view, box plots let you compare distributions across runs."
            >
                <DistributionsSection aggregates={aggregates} />
            </Section>

            <Section
                title="Judge Scores"
                description="LLM-as-judge evaluation across six quality dimensions, each scored 1 to 5. The radar gives a quick multi-dimensional overview; the per-dimension view shows the score distribution and confidence intervals."
            >
                <JudgeSection aggregates={aggregates} />
            </Section>

            {aggregates.length === 1 && (
                <Section
                    title="Persona Stats"
                    description="Session outcomes grouped by persona, verbosity level, or patience bucket. Use the toggle to switch the grouping dimension and the dropdown to change the metric. Error bars show 95% CI of the mean."
                >
                    <PersonaStatsSection aggregates={aggregates} />
                </Section>
            )}

            <Section
                title="Cost Analysis"
                description="In single-run view, sessions are ranked by cost so expensive outliers are immediately visible. The cumulative line shows how total spend grows as sessions complete."
            >
                <CostSection aggregates={aggregates} />
            </Section>

            <Section
                title="Sessions"
                description="All sessions for the selected run(s). Click any row to open the full session detail including judge scores, turn intents, GT comparison, and transcript."
            >
                <SessionsTable aggregates={aggregates} />
            </Section>
        </div>
    )
}
