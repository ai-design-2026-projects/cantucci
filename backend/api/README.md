# backend/api — data-access layer

This package is the **only** place in the codebase permitted to execute SQL.

All other layers (HTTP routers, orchestrator, agents, scripts, notebooks) must
call through this package. SQL anywhere else is an architectural violation per
`CLAUDE.md`.

Nothing here yet — this boundary is reserved for the database access layer.
