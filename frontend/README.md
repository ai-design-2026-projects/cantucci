# CinePal Frontend

React + TypeScript + Vite UI for the CinePal conversational clustering system. The UI presents the evolving cluster map, lets the oracle send messages, and renders cluster snapshots with movie exemplars.

---

## Stack

- **React 19** + **TypeScript 6** — component tree
- **Vite 8** — dev server + build
- **Zustand 5** — client-side session state
- **TanStack Query 5** — server-state fetching and caching
- **React Router v7** — client-side routing
- **Tailwind CSS v4** — utility styling
- **Radix UI** — accessible headless primitives (dialog, dropdown, tooltip, scroll area)
- **Recharts 3** — cluster scatter plot and evaluation charts
- **Framer Motion 12** — animated transitions
- **Sonner** — toast notifications
- **Zod 4** — runtime DTO validation
- **Lucide React** — icons
- **Vitest 4** — unit + component tests

---

## Commands

Run from `frontend/`. Install dependencies and start the dev server with:

```bash
npm install
npm run dev   # Vite dev server at http://localhost:5173
```

| Command | Description |
|---|---|
| `npm install` | Install dependencies |
| `npm run build` | `tsc -b && vite build` — output in `dist/` |
| `npm run typecheck` | Type-check without emitting |
| `npm run lint` | ESLint |
| `npm test` | Vitest single run |
| `npm run test:watch` | Vitest watch mode |

---

## Environment

The dev server proxies `/api` to the backend at `http://localhost:8000`. No extra env vars are needed for local development; the proxy is configured in `vite.config.ts`.

---

## Source layout

```
src/
├── api/
│   ├── client.ts           # base fetch client (auth header injection, error handling)
│   ├── dto/                # Zod schemas + inferred TypeScript types per domain
│   └── services/           # typed service functions per domain (auth, conversations, snapshots, movies, concepts, eval)
├── components/             # shared headless primitives (button, dialog, input, sheet, tooltip, badge, mascot)
├── features/               # feature-scoped components, hooks, and local lib helpers
│   ├── Auth/               # login + register pages and forms
│   ├── AxisDistribution/   # concept axis distribution dialog (beeswarm + density ridge)
│   ├── Chat/               # chat panel, message list, SSE progress, send message flow
│   ├── ClustersInspect/    # cluster inspect modal with movie details popup
│   ├── ClusterSnapshotTab/ # UMAP scatter plot + exemplar cards for the active snapshot
│   ├── EvaluationLab/      # admin-only eval dashboard (run list, KPIs, judge scores, session slide-over)
│   ├── EvolutionMap/       # snapshot DAG modal (radial layout, branch navigation, delete)
│   ├── Header/             # top bar (brand mark, theme toggle, user menu)
│   ├── History/            # conversation history sidebar
│   └── Welcome/            # landing page with start conversation button
├── hooks/                  # cross-feature hooks (app shell, auth hydration)
├── lib/                    # shared utilities (cn, constants)
├── store/                  # Zustand stores (auth, conversation, snapshot, theme)
├── styles/                 # global CSS + Tailwind base + theme tokens
├── App.tsx                 # root component
├── main.tsx                # entry point
└── router.tsx              # route definitions
```
