import { useEffect } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { FlaskConical, PanelLeft } from "lucide-react";
import { ThemeToggle } from "@/components/ThemeToggle";
import { AuthControls } from "@/features/auth/components/AuthControls";
import { useAuthBootstrap } from "@/features/auth/hooks/useAuthBootstrap";
import { useAuthStore } from "@/store/authStore";
import { useUiStore } from "@/store/uiStore";
import { setOn401 } from "@/clients/apiClient";
import { SessionSidebar } from "@/features/session/SessionSidebar";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SIDEBAR_WIDTH = 260;

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
 * Application shell — fixed top bar with branding, theme toggle, auth controls,
 * and a collapsible left session-history sidebar for authenticated users.
 *
 * On /admin routes the shell switches to amber admin chrome and suppresses
 * the session sidebar (the Eval Lab renders its own sidebar inside the page).
 */
export function AppShell() {
  const { status } = useAuthStore();
  const { sidebarOpen, toggleSidebar } = useUiStore();
  const location = useLocation();

  const isAuthenticated = status === "authenticated";
  const isAdminRoute = location.pathname.startsWith("/admin");
  const showSessionSidebar = isAuthenticated && sidebarOpen && !isAdminRoute;
  const showSidebarToggle = isAuthenticated && !isAdminRoute;

  return (
    <>
      <RouterEffects />
      <header
        className={cn(
          "fixed top-0 left-0 right-0 z-50 flex items-center gap-3 px-4 h-[52px] border-b backdrop-blur-[12px] [-webkit-backdrop-filter:blur(12px)]",
          isAdminRoute
            ? "bg-amber-50/90 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800 border-t-2 border-t-amber-500"
            : "bg-background/85 border-border"
        )}
      >
        {showSidebarToggle && (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0"
            onClick={toggleSidebar}
            aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
          >
            <PanelLeft className="h-4 w-4" />
          </Button>
        )}
        {isAdminRoute && (
          <FlaskConical className="h-4 w-4 text-amber-500 shrink-0" />
        )}
        <span
          className={cn(
            "font-display text-lg tracking-tight shrink-0",
            isAdminRoute ? "text-amber-700 dark:text-amber-400" : "text-primary"
          )}
        >
          Cinepal
        </span>
        {isAdminRoute && (
          <span className="inline-flex items-center rounded-full bg-amber-500/15 border border-amber-500/30 px-2 py-0.5 text-[10px] font-semibold text-amber-600 dark:text-amber-400 uppercase tracking-wider">
            Admin Mode
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />
          <AuthControls hideAdminLink={isAdminRoute} />
        </div>
      </header>

      {isAuthenticated && !isAdminRoute && (
        <aside
          className={cn(
            "fixed left-0 top-[52px] z-40 h-[calc(100dvh-52px)] border-r border-border bg-background/95 backdrop-blur-sm overflow-hidden transition-[width] duration-200",
            sidebarOpen ? "w-[260px]" : "w-0"
          )}
          style={{ width: sidebarOpen ? SIDEBAR_WIDTH : 0 }}
        >
          {sidebarOpen && <SessionSidebar />}
        </aside>
      )}

      <div
        className="pt-[52px] transition-[padding-left] duration-200"
        style={{ paddingLeft: showSessionSidebar ? SIDEBAR_WIDTH : 0 }}
      >
        <Outlet />
      </div>
    </>
  );
}
