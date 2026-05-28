import { useState } from 'react'
import { ChevronRight, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

interface JsonTreeProps {
    data: unknown
    depth?: number
    label?: string
}

/**
 * Lightweight collapsible JSON tree. Objects and arrays are collapsible nodes;
 * primitives render inline. No external dependencies.
 */
export function JsonTree({ data, depth = 0, label }: JsonTreeProps) {
    const [open, setOpen] = useState(depth < 2)

    if (data === null || data === undefined) {
        return <JsonLeaf label={label} value="null" valueClass="text-[var(--color-muted)]" />
    }

    if (typeof data === 'boolean') {
        return <JsonLeaf label={label} value={String(data)} valueClass="text-amber-500" />
    }

    if (typeof data === 'number') {
        return <JsonLeaf label={label} value={String(data)} valueClass="text-blue-500" />
    }

    if (typeof data === 'string') {
        return <JsonLeaf label={label} value={`"${data}"`} valueClass="text-emerald-500" />
    }

    if (Array.isArray(data)) {
        const preview = `[${data.length}]`
        return (
            <div style={{ marginLeft: depth > 0 ? 12 : 0 }}>
                <button
                    className="flex items-center gap-1 text-[11px] text-[var(--color-text)] hover:text-[var(--color-primary)] transition-colors"
                    onClick={() => setOpen((o) => !o)}
                >
                    {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                    {label && <span className="text-[var(--color-muted)]">{label}:&nbsp;</span>}
                    <span className={cn('text-[var(--color-muted)]', open && 'opacity-50')}>{preview}</span>
                </button>
                {open && (
                    <div className="ml-3">
                        {data.map((item, i) => (
                            <JsonTree key={i} data={item} depth={depth + 1} label={String(i)} />
                        ))}
                    </div>
                )}
            </div>
        )
    }

    if (typeof data === 'object') {
        const keys = Object.keys(data as object)
        const preview = `{${keys.length}}`
        return (
            <div style={{ marginLeft: depth > 0 ? 12 : 0 }}>
                <button
                    className="flex items-center gap-1 text-[11px] text-[var(--color-text)] hover:text-[var(--color-primary)] transition-colors"
                    onClick={() => setOpen((o) => !o)}
                >
                    {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                    {label && <span className="text-[var(--color-muted)]">{label}:&nbsp;</span>}
                    <span className={cn('text-[var(--color-muted)]', open && 'opacity-50')}>{preview}</span>
                </button>
                {open && (
                    <div className="ml-3">
                        {keys.map((k) => (
                            <JsonTree key={k} data={(data as Record<string, unknown>)[k]} depth={depth + 1} label={k} />
                        ))}
                    </div>
                )}
            </div>
        )
    }

    return <JsonLeaf label={label} value={String(data)} valueClass="text-[var(--color-text)]" />
}

function JsonLeaf({ label, value, valueClass }: { label?: string; value: string; valueClass: string }) {
    return (
        <div className="flex items-baseline gap-1 text-[11px] leading-5" style={{ marginLeft: 16 }}>
            {label && <span className="text-[var(--color-muted)] shrink-0">{label}:</span>}
            <span className={cn('break-all', valueClass)}>{value}</span>
        </div>
    )
}
