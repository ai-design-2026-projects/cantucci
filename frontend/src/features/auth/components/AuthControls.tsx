import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/Spinner";
import { logout } from "@/features/auth/services/authService";
import { useAuthStore } from "@/store/authStore";

interface AuthControlsProps {
  /** When true, the "Admin" link is hidden (used when already on the admin route). */
  hideAdminLink?: boolean;
}

/**
 * Header widget that renders auth state controls.
 *
 * - Anonymous: "Log in" button linking to /login.
 * - Loading: spinner while the bootstrap /auth/me call resolves.
 * - Authenticated: user email, logout button, and (for admins) admin panel button.
 */
export function AuthControls({ hideAdminLink = false }: AuthControlsProps) {
  const { user, status } = useAuthStore();

  if (status === "idle" || status === "loading") {
    return <Spinner size={16} />;
  }

  if (!user) {
    return (
      <Button variant="ghost" size="sm" asChild>
        <Link to="/login">Log in</Link>
      </Button>
    );
  }

  async function handleLogout() {
    try {
      await logout();
    } catch {
      // Proceed even if the server call fails — the cookie will expire naturally.
    }
    window.location.href = "/";
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground hidden sm:inline truncate max-w-[160px]">
        {user.email}
      </span>
      {user.role === "admin" && !hideAdminLink && (
        <Button variant="ghost" size="sm" asChild>
          <Link to="/admin">Eval Lab</Link>
        </Button>
      )}
      <Button variant="ghost" size="sm" onClick={() => void handleLogout()}>
        Log out
      </Button>
    </div>
  );
}
