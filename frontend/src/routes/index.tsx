import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { App } from "@/App";
import { SessionPage } from "@/features/session/SessionPage";
import { LoginPage } from "@/features/auth/pages/LoginPage";
import { RegisterPage } from "@/features/auth/pages/RegisterPage";
import { EvalLabPage } from "@/features/eval/pages/EvalLabPage";
import { ProtectedRoute } from "@/features/auth/components/ProtectedRoute";

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: <App /> },
      { path: "sessions/:sessionId", element: <SessionPage /> },
      { path: "login", element: <LoginPage /> },
      { path: "register", element: <RegisterPage /> },
      {
        element: <ProtectedRoute requireAdmin />,
        children: [{ path: "admin", element: <EvalLabPage /> }],
      },
    ],
  },
]);
