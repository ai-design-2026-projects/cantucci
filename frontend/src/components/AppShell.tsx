import { useEffect } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ThemeToggle } from "@/components/ThemeToggle";
import { AuthControls } from "@/features/auth/components/AuthControls";
import { useAuthBootstrap } from "@/features/auth/hooks/useAuthBootstrap";
import { useAuthStore } from "@/store/authStore";
import { setOn401 } from "@/clients/apiClient";

/**
 * Wires the global 401 handler and runs the auth bootstrap once.
 *
 * Must be rendered inside the router so useNavigate is available.
 */
function RouterEffects() {
  const { reset } = useAuthStore();
  const navigate = useNavigate();

  useEffect(() => {
    setOn401(() => {
      toast.error("Session expired, please log in again.");
      reset();
      navigate("/login");
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useAuthBootstrap();
  return null;
}

/**
 * Application shell — fixed top bar with branding, theme toggle, and auth
 * controls. Page content is rendered via <Outlet />.
 */
export function AppShell() {
  return (
    <>
      <RouterEffects />
      <header className="fixed top-0 left-0 right-0 z-50 flex items-center gap-3 px-6 h-[52px] bg-background/85 border-b border-border backdrop-blur-[12px] [-webkit-backdrop-filter:blur(12px)]">
        <span className="font-display text-lg text-primary tracking-tight shrink-0">
          Cinepal
        </span>
        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />
          <AuthControls />
        </div>
      </header>
      <Outlet />
    </>
  );
}
