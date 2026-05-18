import { useEffect } from "react";
import { fetchMe } from "@/features/auth/services/authService";
import { useAuthStore } from "@/store/authStore";

/**
 * Runs once at app start to resolve the current user from the server.
 *
 * Calls GET /auth/me using the HttpOnly cookie. On success the auth store is
 * set to "authenticated"; on 401 (no cookie or expired) it is set to "anonymous".
 * The 401 from /auth/me never triggers the global on401 toast.
 */
export function useAuthBootstrap(): void {
  const { status, setUser, setStatus } = useAuthStore();

  useEffect(() => {
    if (status !== "idle") return;

    setStatus("loading");
    fetchMe()
      .then((user) => {
        setUser(user);
        setStatus(user ? "authenticated" : "anonymous");
      })
      .catch(() => {
        setUser(null);
        setStatus("anonymous");
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
