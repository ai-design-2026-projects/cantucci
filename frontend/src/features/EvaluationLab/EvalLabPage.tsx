import { Header } from '../Header/Header'
import { RunList } from './RunList/RunList'
import { ConfigPanel } from './ConfigPanel/ConfigPanel'
import { MainArea } from './MainArea/MainArea'
import { SessionSlideOver } from './SessionSlideOver/SessionSlideOver'
import { useEvalLabStore } from './hooks/useEvalLabStore'
import { useRunAggregate, useMultipleRunAggregates } from './hooks/useRunAggregate'

/**
 * Admin-only Eval Lab page. Three-column layout (RunList | MainArea | ConfigPanel)
 * under the shared Header. SessionSlideOver floats on top as a right-side sheet.
 */
export function EvalLabPage() {
    const { selectedRunId, compareMode, compareRunIds } = useEvalLabStore()

    const singleResult = useRunAggregate(compareMode ? null : selectedRunId)
    const multiResults = useMultipleRunAggregates(compareMode ? compareRunIds : [])

    const aggregates = compareMode
        ? multiResults.flatMap((r) => (r.data ? [r.data] : []))
        : singleResult.data
          ? [singleResult.data]
          : []

    const isLoading = compareMode
        ? multiResults.some((r) => r.isLoading)
        : singleResult.isLoading

    const primaryAggregate = compareMode ? null : (singleResult.data ?? null)
    const primaryRun = primaryAggregate?.run ?? null
    const configSnapshot = primaryAggregate?.config_snapshot ?? null

    return (
        <div className="flex flex-col h-screen overflow-hidden bg-[var(--color-bg)]">
            <Header />

            <div className="flex flex-1 min-h-0 pt-14">
                <RunList />

                <MainArea aggregates={aggregates} isLoading={isLoading} />

                <ConfigPanel run={primaryRun} configSnapshot={configSnapshot} />
            </div>

            <SessionSlideOver />
        </div>
    )
}
