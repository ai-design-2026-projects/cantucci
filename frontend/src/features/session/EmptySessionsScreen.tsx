import { Loader2, MessageSquarePlus } from "lucide-react";
import { Mascot } from "@/components/mascot/Mascot";
import { useSessionHandler } from "./hooks/useSessionHandler";

/**
 * Shown to authenticated users who have no sessions yet.
 *
 * Replaces the old auto-create-on-mount behaviour so users consciously
 * start their first chat instead of being silently dropped into one.
 */
export function EmptySessionsScreen() {
  const { createAndNavigate, isCreating } = useSessionHandler();

  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 p-12 text-center">
      <Mascot pose="idle" size={80} />
      <div>
        <p className="font-display text-2xl font-semibold text-foreground tracking-tight">
          No chats yet
        </p>
        <p className="text-sm text-muted-foreground mt-1 max-w-[300px]">
          Start a conversation and CinePal will help you find the right cluster
          of films for your mood.
        </p>
      </div>
      <button
        type="button"
        disabled={isCreating}
        onClick={() => createAndNavigate()}
        className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground shadow-sm hover:bg-primary/90 disabled:opacity-60 transition-colors"
      >
        {isCreating ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <MessageSquarePlus className="h-4 w-4" />
        )}
        Start a chat
      </button>
    </div>
  );
}
