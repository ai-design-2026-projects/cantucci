import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

export const badgeVariants = cva(
    'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors',
    {
        variants: {
            variant: {
                default: 'border-transparent bg-[var(--color-primary)] text-white',
                secondary: 'border-transparent bg-[var(--color-elevated)] text-[var(--color-text)]',
                outline: 'border-[var(--color-border)] text-[var(--color-text)]',
            },
        },
        defaultVariants: { variant: 'default' },
    },
)

/**
 * Small label badge for genres, roles, and tags.
 *
 * @param variant - Visual style variant.
 * @returns Span element styled as a badge.
 */
export function Badge({
    className,
    variant,
    ...props
}: React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof badgeVariants>) {
    return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}
