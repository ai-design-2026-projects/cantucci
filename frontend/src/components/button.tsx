import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

export const buttonVariants = cva(
    'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-ui)] text-sm font-medium transition-colors cursor-pointer disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]',
    {
        variants: {
            variant: {
                default: 'bg-[var(--color-primary)] text-white hover:opacity-90',
                ghost: 'text-[var(--color-text)] hover:bg-[var(--color-elevated)]',
                outline: 'border border-[var(--color-border)] bg-transparent text-[var(--color-text)] hover:bg-[var(--color-elevated)]',
                destructive: 'bg-red-500 text-white hover:bg-red-600',
                link: 'text-[var(--color-primary)] underline-offset-4 hover:underline',
            },
            size: {
                default: 'h-9 px-4 py-2',
                sm: 'h-7 px-3 text-xs',
                lg: 'h-11 px-6',
                icon: 'h-9 w-9',
            },
        },
        defaultVariants: {
            variant: 'default',
            size: 'default',
        },
    },
)

/**
* Styled button component with variants.
*
* @param variant  - Visual style variant.
* @param size     - Size preset.
* @param asChild  - Render as child element via Radix Slot.
* @returns Accessible button element.
*/
export const Button = React.forwardRef<
    HTMLButtonElement,
    React.ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants> & {
        asChild?: boolean
    }
>(
    ({
        className,
        variant,
        size,
        asChild = false,
        ...props
    }, ref) => {
        const Comp = asChild ? Slot : 'button'
        return (
            <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
        )
    })
