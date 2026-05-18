import { useEffect } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { PanelLeft } from "lucide-react";
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
 * Page content is rendered via <Outlet />.
 */
export function AppShell() {
  const { status } = useAuthStore();
  const { sidebarOpen, toggleSidebar } = useUiStore();

  const isAuthenticated = status === "authenticated";
  const showSidebar = isAuthenticated && sidebarOpen;

  return (
    <>
      <RouterEffects />
      <header className="fixed top-0 left-0 right-0 z-50 flex items-center gap-3 px-4 h-[52px] bg-background/85 border-b border-border backdrop-blur-[12px] [-webkit-backdrop-filter:blur(12px)]">
        {isAuthenticated && (
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
        <span className="font-display text-lg text-primary tracking-tight shrink-0">
          Cinepal
        </span>
        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />
          <AuthControls />
        </div>
      </header>

      {isAuthenticated && (
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
        className="transition-[padding-left] duration-200"
        style={{ paddingLeft: showSidebar ? SIDEBAR_WIDTH : 0 }}
      >
        <Outlet />
      </div>
    </>
  );
}
