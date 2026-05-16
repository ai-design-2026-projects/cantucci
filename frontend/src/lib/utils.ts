import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind class strings, resolving conflicts deterministically.
 *
 * Wraps clsx for conditional classes then runs the result through
 * tailwind-merge so duplicate or conflicting utilities collapse to the
 * last-wins winner. This is the standard shadcn/ui helper.
 *
 * @param inputs - Any clsx-compatible class value (strings, arrays, objects).
 * @returns A single merged className string.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
