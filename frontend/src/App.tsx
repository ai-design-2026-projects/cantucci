import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { SessionPage } from "@/features/session/SessionPage";
import { useSessionHandler } from "@/features/session/hooks/useSessionHandler";
import { listSessions } from "@/features/session/services/sessionService";
import { useSessionStore } from "@/store/sessionStore";
import { useAuthStore } from "@/store/authStore";
import { Loader2 } from "lucide-react";

/**
 * Application root (index route at /).
 *
 * Two code paths:
 * - Anonymous: auto-creates a single ephemeral session and renders it inline.
 * - Authenticated: waits for the session list to load, then navigates to the
 *   most recent session (or creates a new one if the list is empty).
 *
 * @returns The bootstrapped session page, a redirect, or a centered spinner.
 */
export function App() {
  const { sessionId } = useSessionStore();
  const { status } = useAuthStore();
  const { initSession, createAndNavigate, isCreating } = useSessionHandler();
  const navigate = useNavigate();

  const bootstrapDone = status === "authenticated" || status === "anonymous";

  const { data: sessions, isLoading: listLoading } = useQuery({
    queryKey: ["sessions", "list"],
    queryFn: listSessions,
    enabled: status === "authenticated",
  });

  useEffect(() => {
    if (!bootstrapDone) return;

    if (status === "anonymous") {
      if (!sessionId) initSession();
      return;
    }

    if (listLoading) return;

    if (sessions && sessions.length > 0) {
      navigate(`/sessions/${sessions[0].session_id}`, { replace: true });
    } else if (!isCreating) {
      createAndNavigate();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bootstrapDone, status, listLoading, sessions]);

  const isWaiting =
    !bootstrapDone ||
    (status === "authenticated" && (listLoading || isCreating)) ||
    (status === "anonymous" && (isCreating || !sessionId));

  if (isWaiting) {
    return (
      <div className="flex items-center justify-center h-dvh bg-background">
        <Loader2 className="h-10 w-10 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (status === "authenticated") {
    return null;
  }

  return <SessionPage />;
}
