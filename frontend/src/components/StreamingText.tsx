import type { ReactNode } from "react";

interface StreamingTextProps {
  /** Full text to render. Currently renders instantly; SSE streaming is a future addition. */
  text: string;
  /** Optional className forwarded to the wrapping span. */
  className?: string;
}

/**
 * Renders text content from the assistant.
 *
 * Today this is a passthrough — text appears immediately on mount.
 * The component surface is reserved for future token-by-token SSE streaming
 * without requiring component-level refactoring.
 *
 * @param text - Full text string to display.
 * @param className - Optional CSS class name.
 * @returns A span containing the text.
 */
export function StreamingText({ text, className }: StreamingTextProps): ReactNode {
  return <span className={className}>{text}</span>;
}
