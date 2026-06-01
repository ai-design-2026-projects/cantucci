import { useState } from 'react'
import { Users } from 'lucide-react'
import { Button } from '@/components/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/dialog'
import type { EvalSessionDetailDto } from '@/api/dto/eval'

interface PersonaDialogProps {
    session: EvalSessionDetailDto
}

/**
 * Button and dialog that surfaces the persona config (verbosity, patience)
 * and ground truth (intent description, operations) for the session.
 */
export function PersonaDialog({ session }: PersonaDialogProps) {
    const [open, setOpen] = useState(false)
    const { persona, ground_truth } = session

    if (!persona && !ground_truth) return null

    return (
        <>
            <Button variant="outline" size="sm" className="gap-1.5 text-xs" onClick={() => setOpen(true)}>
                <Users className="h-3.5 w-3.5" />
                View personas
            </Button>

            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="max-w-lg w-full p-0 flex flex-col max-h-[85vh]">
                    <DialogHeader className="px-6 pt-5 pb-4 border-b border-[var(--color-border)] shrink-0">
                        <DialogTitle className="text-sm">Persona and ground truth</DialogTitle>
                    </DialogHeader>

                    <div className="overflow-y-auto scrollbar-styled flex flex-col gap-6 px-6 py-5">
                        {persona && (
                            <section className="flex flex-col gap-3">
                                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
                                    Persona
                                </h3>
                                <table className="w-full text-xs border-collapse">
                                    <tbody>
                                        {[
                                            { label: 'Slug', value: persona.slug },
                                            { label: 'Verbosity', value: persona.verbosity },
                                            { label: 'Patience', value: persona.patience.toFixed(2) },
                                        ].map(({ label, value }) => (
                                            <tr key={label} className="border-b border-[var(--color-border)]">
                                                <td className="py-1.5 pr-4 text-[var(--color-muted)] font-medium w-1/3">{label}</td>
                                                <td className="py-1.5 text-[var(--color-text)]">{value}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </section>
                        )}

                        {ground_truth && (
                            <section className="flex flex-col gap-3">
                                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
                                    Ground truth
                                </h3>
                                <p className="text-xs text-[var(--color-muted)] leading-relaxed">
                                    <span className="font-medium text-[var(--color-text)]">Intent: </span>
                                    {ground_truth.intent_description}
                                </p>
                                <div>
                                    <p className="text-[10px] uppercase tracking-wide text-[var(--color-muted)] mb-2">
                                        Target trajectory
                                    </p>
                                    <div className="flex flex-col gap-1.5">
                                        {ground_truth.operations.map((op, i) => (
                                            <div key={i} className="flex items-start gap-2">
                                                <span className="text-[10px] font-mono text-[var(--color-muted)] shrink-0 mt-0.5 w-4 text-right">
                                                    {i + 1}.
                                                </span>
                                                <div className="flex flex-wrap gap-1 text-[11px]">
                                                    <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-border)] text-[var(--color-muted)]">
                                                        {op.op}
                                                    </span>
                                                    {op.concept && (
                                                        <span className="text-[var(--color-text)]">{op.concept}</span>
                                                    )}
                                                    {op.kind && (
                                                        <span className="text-[10px] px-1 py-0.5 rounded bg-sky-400/15 text-sky-600">
                                                            {op.kind}
                                                        </span>
                                                    )}
                                                    {op.space && (
                                                        <span className="text-[10px] px-1 py-0.5 rounded bg-violet-400/15 text-violet-600">
                                                            {op.space}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </section>
                        )}
                    </div>
                </DialogContent>
            </Dialog>
        </>
    )
}
