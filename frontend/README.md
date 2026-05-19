# CinePal Frontend

React + Vite UI for the CinePal conversational clustering system. The frontend presents the session flow: create a session, send oracle messages, inspect the conversation, and view the converged cluster plus movie details when the backend declares convergence.

---

## Overview

### Prerequisites

- Node.js 18+
- npm
- The backend reachable at the host the Vite proxy points to (configurable via `VITE_API_BASE`; defaults to `http://127.0.0.1:8000`)

### Setup

```bash
npm install
```

### Run locally

```bash
npm run dev
```

Vite runs on <http://127.0.0.1:5173> and proxies API requests to the FastAPI backend.

### Typecheck and tests

```bash
npm run typecheck
npm run test
```

### Production build

```bash
npm run build
```

### Running via Docker

The published frontend image is nginx serving the pre-built Vite bundle. It proxies `/sessions`, `/movies`, and `/auth` to a `backend` host on port 8000, so it is designed to run alongside the backend container (e.g. via `docker compose`).

```bash
# Intended usage — the backend service must be reachable as hostname "backend"
docker compose up -d   # from the repo root
# UI at http://localhost
```

The nginx proxy configuration is in `frontend/nginx.conf`. SPA routes (e.g. `/session/123`) fall back to `index.html` automatically.

---

## Repository Structure

```
frontend/
  index.html          Vite entry HTML and font loading.
  package.json        Scripts, dependencies, and test config.
  vite.config.ts      Vite aliasing, dev proxy, Vitest setup.
  tsconfig.json       Strict TypeScript configuration.
  src/
    main.tsx          App bootstrap and query client provider.
    App.tsx           Session bootstrap and top-level page switch.
    clients/          API client and shared React Query client.
    components/       Reusable design-system components.
    features/         Session, conversation, clusters, and eval screens.
    store/            Zustand state for session, UI, and cluster state.
    styles/           Global CSS, animations, and shared module styles.
    tests/            Vitest setup and component / feature tests.
    utils/            Shared types and formatting helpers.
```

---

## UI Flow

- The app creates a session on first mount and stores the `session_id` in Zustand.
- Conversation turns are submitted through the shared API client and cached with TanStack Query.
- When the backend returns `converged=true`, the reveal view loads the converged cluster payload and movie details.
- Movie cards open a detail modal backed by the `/movies/{movie_id}` endpoint.

---

## Notes

- API calls go through `src/clients/apiClient.ts`; the Vite dev server proxies `/sessions` and `/movies` to the backend.
- Shared design-system components live in `src/components/`; feature-specific UI and CSS live in `src/features/`.
- CSS modules are stored under `src/styles/` and feature-local `styles/` folders.
- `src/vite-env.d.ts` declares CSS module types for TypeScript.
- `src/tests/setup.ts` loads `@testing-library/jest-dom` for Vitest.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE` | `""` | Optional API base URL. Defaults to same-origin requests through the Vite proxy. |

---

## Scripts

| Script | Description |
|---|---|
| `npm run dev` | Start the Vite development server. |
| `npm run build` | Typecheck and build the frontend for production. |
| `npm run preview` | Preview the production build locally. |
| `npm run typecheck` | Run `tsc --noEmit`. |
| `npm run test` | Run the Vitest suite once. |
| `npm run test:watch` | Run Vitest in watch mode. |
