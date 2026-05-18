import { useRef, useState, type KeyboardEvent } from "react";
import { Loader2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ComposerProps {
  /** Whether a turn is in-flight. Disables the input and send button. */
  isLoading: boolean;
  /** Called with the composed message when the oracle submits. */
  onSubmit: (message: string) => void;
}

/**
 * Text input area for the oracle to compose and submit messages.
 *
 * Submits on Enter (without Shift). Ctrl+Enter / Cmd+Enter also submits.
 * Clears the input on successful submission. The textarea grows with content
 * up to 160px; the send button anchors to the bottom edge of the composer.
 *
 * @param isLoading - Disables input while a turn is pending.
 * @param onSubmit - Receives the trimmed message string.
 * @returns The composer form element.
 */
export function Composer({ isLoading, onSubmit }: ComposerProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleSubmit() {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    onSubmit(trimmed);
    setValue("");
    textareaRef.current?.focus();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.key === "Enter" && !e.shiftKey) || (e.key === "Enter" && (e.ctrlKey || e.metaKey))) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="flex items-end gap-2 pt-3 pb-4 border-t border-border-subtle bg-background sticky bottom-0">
      <textarea
        ref={textareaRef}
        className="flex-1 min-h-[56px] max-h-40 bg-card border border-border rounded-md text-foreground text-[0.9375rem] leading-relaxed px-3.5 py-3 resize-none transition-colors focus:outline-none focus:border-border-strong placeholder:text-muted-foreground disabled:opacity-50"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Tell me what you want to watch…"
        rows={1}
        disabled={isLoading}
        aria-label="Oracle message"
      />
      <Button
        variant="default"
        size="icon"
        onClick={handleSubmit}
        disabled={!value.trim() || isLoading}
        className="min-h-[56px] min-w-[56px] shrink-0 self-end"
        aria-label="Send message"
      >
        {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
      </Button>
    </div>
  );
}
