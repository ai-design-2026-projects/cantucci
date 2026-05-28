import { PanelRightClose, PanelRightOpen } from 'lucide-react'
import { Button } from '@/components/button'
import { cn } from '@/lib/utils'
import type { RunDto } from '@/api/dto/eval'
import { JsonTree } from './JsonTree'
import { useEvalLabStore } from '../hooks/useEvalLabStore'

interface ConfigPanelProps {
    run: RunDto | null
    configSnapshot: Record<string, unknown> | null
}

const STATUS_COLORS: Record<string, string> = {
    running: 'text-yellow-500',
    completed: 'text-emerald-500',
    aborted: 'text-red-500',
}

/**
 * Hideable right panel showing the selected run's metadata and collapsible
 * JSON tree of its config_snapshot. Collapsed to an icon strip when hidden.
 */
export function ConfigPanel({ run, configSnapshot }: ConfigPanelProps) {
    const { configPanelOpen, setConfigPanelOpen } = useEvalLabStore()

    return (
        <div className={cn(
            'flex-shrink-0 flex flex-col border-l border-[var(--color-border)] bg-[var(--color-surface)] transition-all duration-200 overflow-hidden',
            configPanelOpen ? 'w-72' : 'w-10',
        )}>
            <div className={cn(
                'flex items-center border-b border-[var(--color-border)] h-12 flex-shrink-0',
                configPanelOpen ? 'justify-between px-3' : 'justify-center',
            )}>
                {configPanelOpen && (
                    <span className="text-sm font-medium text-[var(--color-text)]">Config</span>
                )}
                <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => setConfigPanelOpen(!configPanelOpen)}
                >
                    {configPanelOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
                </Button>
            </div>

            {configPanelOpen && (
                <div className="flex-1 overflow-y-auto">
                    {!run ? (
                        <p className="text-xs text-[var(--color-muted)] px-4 py-4">Select a run to view its config.</p>
                    ) : (
                        <div className="flex flex-col gap-0">
                            <div className="px-4 py-3 border-b border-[var(--color-border)] flex flex-col gap-1.5">
                                <div className="text-xs font-semibold text-[var(--color-text)] break-all">
                                    {run.name ?? run.id.slice(0, 12)}
                                </div>

                                {[
                                    ['Condition', run.condition],
                                    ['Model', run.model_version],
                                    ['Config hash', run.config_hash],
                                    ['Seed', String(run.seed)],
                                ].map(([k, v]) =>
                                    v ? (
                                        <div key={k} className="flex justify-between gap-2">
                                            <span className="text-[11px] text-[var(--color-muted)]">{k}</span>
                                            <span className="text-[11px] text-[var(--color-text)] font-mono break-all text-right">{v}</span>
                                        </div>
                                    ) : null
                                )}

                                <div className="flex justify-between gap-2">
                                    <span className="text-[11px] text-[var(--color-muted)]">Status</span>
                                    <span className={cn('text-[11px] font-medium', STATUS_COLORS[run.status])}>
                                        {run.status}
                                    </span>
                                </div>

                                {run.started_at && (
                                    <div className="flex justify-between gap-2">
                                        <span className="text-[11px] text-[var(--color-muted)]">Started</span>
                                        <span className="text-[11px] text-[var(--color-text)]">
                                            {new Date(run.started_at).toLocaleString()}
                                        </span>
                                    </div>
                                )}

                                {run.ended_at && (
                                    <div className="flex justify-between gap-2">
                                        <span className="text-[11px] text-[var(--color-muted)]">Ended</span>
                                        <span className="text-[11px] text-[var(--color-text)]">
                                            {new Date(run.ended_at).toLocaleString()}
                                        </span>
                                    </div>
                                )}

                                {run.notes && (
                                    <p className="text-[11px] text-[var(--color-muted)] italic">{run.notes}</p>
                                )}
                            </div>

                            {configSnapshot && (
                                <div className="px-3 py-3">
                                    <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2">
                                        Config snapshot
                                    </p>
                                    <JsonTree data={configSnapshot} />
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
