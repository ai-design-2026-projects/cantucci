import { useEffect } from "react";
import { SessionPage } from "@/features/session/SessionPage";
import { useSessionHandler } from "@/features/session/hooks/useSessionHandler";
import { useSessionStore } from "@/store/sessionStore";
import { Loader2 } from "lucide-react";

/**
 * Application root.
 *
 * Boots a session on first mount, then hands off to SessionPage.
 * No routing is needed for this single-page MVP.
 *
 * @returns The bootstrapped session page, or a centered spinner while initialising.
 */
export function App() {
  const { sessionId } = useSessionStore();
  const { initSession, isCreating } = useSessionHandler();

  useEffect(() => {
    if (!sessionId) initSession();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (isCreating || !sessionId) {
    return (
      <div className="flex items-center justify-center h-dvh bg-background">
        <Loader2 className="h-10 w-10 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return <SessionPage />;
}
