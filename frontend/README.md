# CinePal Frontend

React + TypeScript + Vite UI for the CinePal conversational clustering system. The UI presents the evolving cluster map, lets the oracle send messages, and renders cluster snapshots with movie exemplars.

---

## Stack

- **React 19** + **TypeScript** — component tree
- **Vite** — dev server + build
- **Zustand** — client-side session state
- **TanStack Query** — server-state fetching and caching
- **React Router v7** — client-side routing
- **Tailwind CSS v4** — utility styling
- **Radix UI** — accessible headless primitives
- **Recharts** — cluster map visualisation
- **Framer Motion** — animated transitions
- **Vitest** — unit + component tests

---

## Commands

Run from `frontend/`:

```bash
npm install          # install deps
npm run dev          # Vite dev server at http://localhost:5173
npm run build        # tsc -b && vite build (output in dist/)
npm run typecheck    # type-check without emitting
npm run lint         # ESLint
npm test             # vitest single run
npm run test:watch   # vitest watch mode
```

---

## Environment

The dev server proxies `/api` to the backend running on `http://localhost:8000`. No extra env vars are needed for local development; the proxy is configured in `vite.config.ts`.

---

## Layout

```
src/
  api/          Typed fetch clients for backend endpoints
  components/   Shared UI primitives (buttons, dialogs, …)
  features/     Feature-scoped components and hooks
  hooks/        Cross-feature custom hooks
  lib/          Utilities (cn, formatters, …)
  store/        Zustand stores
  styles/       Global CSS + Tailwind base
  App.tsx        Root component
  main.tsx       Entry point
  router.tsx     Route definitions
```
