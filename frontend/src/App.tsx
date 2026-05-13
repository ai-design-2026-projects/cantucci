import { useEffect } from "react";
import { SessionPage } from "@/features/session/SessionPage";
import { useSessionHandler } from "@/features/session/hooks/useSessionHandler";
import { useSessionStore } from "@/store/sessionStore";
import { Spinner } from "@/components/Spinner";

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
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100dvh",
          background: "var(--bg-base)",
        }}
      >
        <Spinner size={40} />
      </div>
    );
  }

  return <SessionPage />;
}
