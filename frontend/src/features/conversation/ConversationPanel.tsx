import { useEffect, useRef } from "react";
import { Composer } from "./Composer";
import { MessageBubble } from "./MessageBubble";
import { useFetchTurns } from "./hooks/useFetchTurns";
import { useTurnHandler } from "./hooks/useTurnHandler";
import type { TurnResult } from "@/utils/types";

interface ConversationPanelProps {
  /** Active session UUID. */
  sessionId: string;
  /** When true, disables the Composer (terminal session state). */
  isTerminal?: boolean;
}

/**
 * Main conversation area: message history and composer.
 *
 * Data comes from useFetchTurns; mutations go through useTurnHandler.
 * No business logic lives here — only composition of sub-components.
 *
 * @param sessionId - UUID of the active session.
 * @param isTerminal - Disables the Composer when the session has ended.
 * @returns The full conversation panel.
 */
export function ConversationPanel({ sessionId, isTerminal = false }: ConversationPanelProps) {
  const turns = useFetchTurns(sessionId);
  const { submitTurn, isPending } = useTurnHandler();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns.length]);

  function handleSubmit(message: string) {
    submitTurn({ sessionId, userMessage: message });
  }

  function handleChoose(choice: string) {
    submitTurn({ sessionId, userMessage: choice });
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden" aria-label="Conversation">
      <div className="flex-1 overflow-y-auto pt-6 pb-2 flex flex-col gap-5 scroll-smooth" role="log" aria-live="polite">
        {turns.length === 0 && (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 px-6 py-12 text-center text-muted-foreground">
            <p className="font-display text-[1.375rem] text-foreground tracking-tight">
              What do you want to watch?
            </p>
            <p className="text-[0.9375rem] max-w-[360px] leading-[1.55]">
              Describe a mood, a genre, a favourite director — anything. I will
              find the right cluster of films for you.
            </p>
          </div>
        )}

        {turns.map((turn: TurnResult, i: number) => (
          <MessageBubble
            key={turn.turn_id}
            turn={turn}
            isLast={i === turns.length - 1}
            onChoose={handleChoose}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {!isTerminal && (
        <Composer isLoading={isPending} onSubmit={handleSubmit} />
      )}
    </div>
  );
}
