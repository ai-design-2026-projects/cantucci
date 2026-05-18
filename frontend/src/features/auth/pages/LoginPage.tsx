import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/Spinner";
import { ApiError, type FieldErrors } from "@/clients/apiClient";
import { login } from "@/features/auth/services/authService";
import { useAuthStore } from "@/store/authStore";

/**
 * Login page with email/password form.
 *
 * - 422 field errors are shown inline under the relevant input.
 * - All other errors (401 Invalid credentials, network, 5xx) appear as toasts.
 * - Redirects authenticated users to / immediately.
 */
export function LoginPage() {
  const { user, setUser, setStatus } = useAuthStore();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  if (user) {
    return <Navigate to="/" replace />;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFieldErrors({});
    setSubmitting(true);
    try {
      const loggedInUser = await login(email, password);
      setUser(loggedInUser);
      setStatus("authenticated");
      navigate("/");
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length > 0) {
        setFieldErrors(err.fieldErrors);
      } else {
        toast.error(err instanceof ApiError ? err.detail : "Something went wrong. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex items-center justify-center min-h-[calc(100dvh-52px)] bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Log in</h1>
          <p className="text-sm text-muted-foreground">Enter your credentials to continue.</p>
        </div>

        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4" noValidate>
          <div className="space-y-1">
            <label htmlFor="email" className="text-sm font-medium">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="you@example.com"
            />
            {fieldErrors.email && (
              <p className="text-xs text-destructive">{fieldErrors.email}</p>
            )}
          </div>

          <div className="space-y-1">
            <label htmlFor="password" className="text-sm font-medium">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="Min. 8 characters"
            />
            {fieldErrors.password && (
              <p className="text-xs text-destructive">{fieldErrors.password}</p>
            )}
          </div>

          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? <Spinner size={16} /> : "Log in"}
          </Button>
        </form>

        <p className="text-center text-sm text-muted-foreground">
          Don&apos;t have an account?{" "}
          <Link to="/register" className="font-medium text-primary hover:underline">
            Register
          </Link>
        </p>

        <p className="text-center text-sm text-muted-foreground">
          <Link to="/" className="font-medium text-primary hover:underline">
            &larr; Back to home
          </Link>
        </p>
      </div>
    </div>
  );
}
