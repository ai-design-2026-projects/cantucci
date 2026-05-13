# LLM-Oracle Evaluation Harness — Injection Surface

This directory is reserved for the future LLM-Oracle evaluation harness.

## Human-to-LLM oracle swap

The single injection point for swapping oracles is `useTurnHandler.submitTurn` in
`src/features/conversation/hooks/useTurnHandler.ts`. The harness replaces (or wraps)
the `Composer` component with a programmatic driver that calls the same hook with the
same `{ sessionId, userMessage }` parameter shape. No view changes are needed.

## Session store

`sessionStore.oracleType` is pre-wired as `"human" | "llm"` (defaults to `"human"`).
The evaluation harness sets it to `"llm"` via `useSessionStore.getState().oracleType = "llm"`
before bootstrapping the session. `SessionHeader` displays the badge; no other component
branches on it.

## Reveal data path

`useFetchConvergedCluster` returns `ConvergedClusterPublic` regardless of oracle type.
The reveal screen is oracle-agnostic; the harness can read convergence outcomes the
same way the human UI does.

## Integration points (not yet implemented)

- `src/features/eval/LLMOracleDriver.tsx` — programmatic composer that calls `useTurnHandler`
- `src/features/eval/useEvalSession.ts` — runs a full session loop and collects metrics
- `src/features/eval/evalConfig.ts` — target cluster ids, max turns, assertion criteria
