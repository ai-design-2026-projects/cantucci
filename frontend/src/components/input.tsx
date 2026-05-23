import * as React from 'react'
import { cn } from '@/lib/utils'

/**
 * Text input with theme-aware styling.
 *
 * @param className - Additional class names.
 * @returns Styled input element.
 */
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
    ({
        className,
        type,
        ...props
    }, ref) => {
        return (
            <input
                type={type}
                className={cn(
                    'flex h-9 w-full rounded-[var(--radius-ui)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-sm text-[var(--color-text)] placeholder:text-[var(--color-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)] disabled:cursor-not-allowed disabled:opacity-50 transition-colors',
                    className,
                )}
                ref={ref}
                {...props}
            />
        )
    })
