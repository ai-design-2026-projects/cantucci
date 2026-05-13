import { useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/Button";
import { Spinner } from "@/components/Spinner";
import styles from "./styles/Conversation.module.css";

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
 * Clears the input on successful submission.
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
    <div className={styles.composer}>
      <textarea
        ref={textareaRef}
        className={styles.composerInput}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Tell me what you want to watch…"
        rows={2}
        disabled={isLoading}
        aria-label="Oracle message"
      />
      <Button
        variant="primary"
        onClick={handleSubmit}
        disabled={!value.trim() || isLoading}
        className={styles.composerSend}
        aria-label="Send message"
      >
        {isLoading ? <Spinner size={16} /> : "Send"}
      </Button>
    </div>
  );
}
