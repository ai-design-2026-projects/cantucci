import { Link } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";

/**
 * Admin panel placeholder.
 *
 * Protected by ProtectedRoute (requireAdmin=true) — only reachable by users
 * with the "admin" role. Content is a placeholder pending future admin tooling.
 */
export function AdminPage() {
  const { user } = useAuthStore();

  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100dvh-52px)] bg-background px-4">
      <div className="w-full max-w-md space-y-4 text-center">
        <h1 className="text-3xl font-semibold tracking-tight">Admin Panel</h1>
        <p className="text-sm text-muted-foreground">
          Logged in as <span className="font-medium text-foreground">{user?.email}</span>.
        </p>
        <p className="text-sm text-muted-foreground">
          Admin tooling will appear here in a future release.
        </p>
        <Link to="/" className="text-sm font-medium text-primary hover:underline">
          &larr; Back to home
        </Link>
      </div>
    </div>
  );
}
