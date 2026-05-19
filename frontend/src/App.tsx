import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { SessionPage } from "@/features/session/SessionPage";
import { EmptySessionsScreen } from "@/features/session/EmptySessionsScreen";
import { useSessionHandler } from "@/features/session/hooks/useSessionHandler";
import { listSessions } from "@/features/session/services/sessionService";
import { useSessionStore } from "@/store/sessionStore";
import { useAuthStore } from "@/store/authStore";
import { Loader2 } from "lucide-react";

/**
 * Application root (index route at /).
 *
 * Three code paths:
 * - Anonymous: auto-creates a single ephemeral session and renders it inline.
 * - Authenticated, has sessions: navigates to the most recent session.
 * - Authenticated, no sessions: renders ``EmptySessionsScreen`` so the user
 *   consciously starts their first chat.
 *
 * @returns The bootstrapped session page, a redirect, the empty state, or a spinner.
 */
export function App() {
  const { sessionId } = useSessionStore();
  const { status } = useAuthStore();
  const { initSession, isCreating } = useSessionHandler();
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
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bootstrapDone, status, listLoading, sessions]);

  const isWaiting =
    !bootstrapDone ||
    (status === "authenticated" && listLoading) ||
    (status === "anonymous" && (isCreating || !sessionId));

  if (isWaiting) {
    return (
      <div className="flex items-center justify-center h-dvh bg-background">
        <Loader2 className="h-10 w-10 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (status === "authenticated" && sessions && sessions.length === 0) {
    return <EmptySessionsScreen />;
  }

  if (status === "authenticated") {
    return null;
  }

  return <SessionPage />;
}
