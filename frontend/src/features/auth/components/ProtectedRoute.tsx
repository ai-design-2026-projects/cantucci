import { Navigate, Outlet } from "react-router-dom";
import { toast } from "sonner";
import { Spinner } from "@/components/Spinner";
import { useAuthStore } from "@/store/authStore";

interface ProtectedRouteProps {
  /** When true, also requires the user to have the "admin" role. */
  requireAdmin?: boolean;
}

/**
 * Layout route element that guards access based on authentication status.
 *
 * - Loading: renders a centered spinner until bootstrap resolves.
 * - Anonymous: redirects to /login.
 * - Non-admin on requireAdmin route: redirects to / with a toast.
 * - Otherwise: renders the child route via <Outlet />.
 */
export function ProtectedRoute({ requireAdmin = false }: ProtectedRouteProps) {
  const { user, status } = useAuthStore();

  if (status === "idle" || status === "loading") {
    return (
      <div className="flex items-center justify-center h-dvh bg-background">
        <Spinner size={40} />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (requireAdmin && user.role !== "admin") {
    toast.error("Admin access required.");
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
