# backend/CLAUDE.md

Backend-specific conventions for Claude Code. Top-level `CLAUDE.md` covers repo-wide rules; this file is the backend deep-dive.

---

## Type layering

Three layers exist, with conversion flowing in one direction only:

```
data_access/<domain>/types.py  →  agents/<name>/types.py  →  routers/dto/<domain>/dtos.py
        (Row)                         (agent-internal)               (Dto / wire)
```

**`backend/data_access/<domain>/types.py`** — `@dataclass(frozen=True, slots=True)` row types and aggregates. No HTTP knowledge, no Pydantic. Each row type carries a `from_row(cls, r: dict) -> "XRow"` classmethod that reads columns by name from a psycopg `dict_row` cursor result.

**`backend/agents/<name>/types.py`** — `@dataclass(frozen=True, slots=True)` agent-internal types (results, enums). LLM-derived result types carry `from_llm_response(cls, parsed: BaseModel, ...) -> "X"` to encapsulate construction from a structured LLM response. Drafts that need to be built up incrementally (e.g. `ClusterDraft`, `ClusterSnapshotDraft`) use `frozen=True, slots=True` as well — all incremental construction is done by building a local list then passing it to the constructor in one call, never by mutating a field post-construction.

**`backend/routers/dto/<domain>/dtos.py`** — Pydantic wire models. Constructed from row types inside router handlers. `User` (in `backend/auth/types.py`) is the one accepted straddler — it is a Pydantic model used as a dependency injection type on the HTTP layer, not to be widened.

### Direction rule

**Row → agent-internal → DTO.** Never the reverse. Inbound HTTP payloads are Pydantic request DTOs that the router unpacks into primitives before calling `data_access/` or `agents/`. Row → DTO conversion stays inline in router handlers (presentation logic belongs in the presentation layer).

---

## Dataclass vs Pydantic

Use `@dataclass` for all internal types. Use Pydantic only at the wire boundary (request/response DTOs in `routers/dto/`). Internal invariants are enforced by `from_row` / `from_llm_response` constructors and mypy strict, not runtime validation.

---

## Naming conventions

| Suffix | Layer | Example |
|---|---|---|
| `XRow` | DB-shaped (`data_access/`) | `ClusterSnapshotRow`, `MovieSearchHitRow` |
| `XDto` | Wire (`routers/dto/`) | `ClusterSnapshotDto`, `MovieStubDto` |
| *(no suffix)* | Agent-internal (`agents/`) | `IntentResult`, `ClusterDraft` |

New code must follow this. `MovieSearchHitRow` is the canonical name — the old `MovieSearchHit` alias has been removed.

---

## `from_row` — DB → domain type conversion

`data_access/connection.py` sets `conn.row_factory = dict_row` on every connection, so every `cursor.execute(...).fetchone()` returns a dict. All row dataclasses read by name:

```python
@dataclass(frozen=True, slots=True)
class ClusterSnapshotRow:
    id: uuid.UUID
    conversation_id: uuid.UUID | None
    ...

    @classmethod
    def from_row(cls, r: dict) -> "ClusterSnapshotRow":
        return cls(
            id=r["id"],
            conversation_id=r["conversation_id"],
            ...
        )
```

`data_access/<domain>/queries.py` calls `Row.from_row(r)` instead of hand-building. Robust to SELECT column reordering; dict allocation cost is negligible at our query volume.

---

## `from_llm_response` — LLM output → agent type conversion

Agent-internal dataclasses that come from LLM output carry:

```python
@dataclass(frozen=True, slots=True)
class IntentResult:
  navigationMode: NavigationMode
    ...

    @classmethod
    def from_llm_response(cls, parsed: BaseModel, raw_content: str) -> "IntentResult":
        ...
```

The agent calls `IntentResult.from_llm_response(parsed, raw_content=resp.content)`. All normalisation logic (UUID parsing, fallback values) lives on the dataclass, not scattered in agent code. For plain-text LLM responses (no structured JSON), the signature accepts the content string directly:

```python
@classmethod
def from_llm_response(cls, content: str, ...) -> "ExplanationResult":
    return cls(text=content, ...)
```

---

## Agent module conventions

Every agent under `backend/agents/<name>/` must follow this layout:

```
backend/agents/<name>/
  agent.py        # XLLMAgent subclass + module-level wrapper function
  types.py        # XLLMResponse(BaseModel) wire schema + XResult(@dataclass frozen/slots)
  parser.py       # (Optional) Pure functions for parsing when side effects are needed
  scoring.py      # (Optional) Pure scoring/utility functions unrelated to the LLM call
  prompts/
    <fn>_v1.j2    # Versioned Jinja2 templates — keep old files for replay
    <fn>_v2.j2    # New version; agent.py loads the latest
  __init__.py     # Empty
```

**Canonical agent shape** (`intent` agent is the reference implementation):

All functional agents subclass `LLMAgent` from `backend.agents.base` and are accessed
through a module-level wrapper function whose signature matches the public API. Call
sites never reference the class directly.

1. `types.py` defines exactly two types:
   - `XLLMResponse(BaseModel)` — Pydantic wire schema matching the JSON the LLM returns.
   - `XResult(@dataclass(frozen=True, slots=True))` — internal result. Must include a
     `cost: float` field populated from `resp.cost_usd`. Carries a
     `from_llm_response(cls, parsed, cost, ...)` classmethod for all normalization logic
     (UUID coercion, enum mapping, fallbacks). No I/O in `from_llm_response`.

2. `agent.py` defines a subclass and a module-level singleton + wrapper:
   ```python
   class XLLMAgent(LLMAgent[XResult]):
       name = "x"                       # resolves prompts_dir("x")
       step_type = "x_agent"
       model_tier = "strong"            # or "fast"
       template_name = "x_v1.j2"
       response_schema = XLLMResponse   # None for plain-text agents

       async def render_kwargs(self, **inputs): ...   # build template vars
       def build_result(self, resp, **inputs): ...    # from_llm_response + log.info

   _agent = XLLMAgent()

   async def do_x(...) -> XResult:
       """Public API docstring."""
       return await _agent.run(...)
   ```
   `render_kwargs` and `build_result` receive the same merged inputs (including the
   standard trio: `conversation_id`, `message_id`, `accumulated_cost`).

3. When pre-LLM I/O is needed (e.g. DB fetches), override `run` and delegate to
   `super().run(...)` after enriching inputs (see the explanation agent).

4. When parsing requires side effects (embedding lookups, vector search), move that
   logic into `parser.py` as plain functions (`parse_concept`, `build_linear_axis`, …).
   `build_result` calls into `parser.py`; the dataclass classmethod stays pure.

5. **No fallback returns on parse failure.** Raise `LLMParseError` or a `DomainError`
   subclass and let the global handler translate. The harness already retries transient
   errors; silent fallbacks hide real bugs.

6. **Prompt versioning:** every prompt change = new `_vN.j2` file. Old files stay for
   replay. Update `template_name` on the subclass.

7. **Cost aggregation:** the coordinator accumulates cost via `result.cost` on each
   agent's return value. Never re-inspect `LLMResponse.cost_usd` outside the agent.

---

## Aggregates / composite types

Types composed of multiple row types at the same layer (e.g. `ClusterSnapshotWithClusters`) live in the same `data_access/<domain>/types.py` as their component rows. They are not produced by `from_row` — they are assembled in `queries.py` by combining individual `from_row` calls.

---

## ID type aliases

Raw `uuid.UUID` and `int` are used throughout. A `NewType` pass over `data_access/` + `agents/` would catch mis-passed-ID bugs at mypy time, but adoption cost is non-trivial. Documented here as a future option — not adopted in the current codebase.

---

## Exception taxonomy

Single base in `backend/exceptions.py`:

```python
class DomainError(Exception):
    """Base for all application-meaningful failures the HTTP layer should translate."""
    http_status: int = 500
```

### Families

| Class | `http_status` | Subclasses |
|---|---|---|
| `NotFoundError(DomainError)` | 404 | `ConversationNotFound`, `ClusterSnapshotNotFound`, `MovieNotFound` |
| `ParseError(DomainError)` | 422 | `ConceptParseError` |
| `AuthError(DomainError)` | 401 | `InvalidToken`, `TokenExpired` |
| `OperationalError(DomainError)` | 500 | `CostLimitExceeded`, `LLMParseError`, `ReplayDriftError` |

LLM-specific exceptions (`CostLimitExceeded`, `LLMParseError`, `ReplayDriftError`) live in `backend/llm/exceptions.py` and inherit from the cross-cutting families above.

### Global handler

Registered in `backend/app.py`:

```python
@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content={"detail": str(exc)})
```

Routers raise the domain exception directly — `raise ConversationNotFound(conversation_id)` — and never construct `HTTPException` themselves for domain failures.

### Where exceptions live

- `backend/exceptions.py` — cross-cutting domain exceptions (NotFound, Parse, Auth, Operational families).
- `backend/llm/exceptions.py` — LLM-specific subclasses of the operational/parse families.
- `<package>/exceptions.py` — package-local exceptions that don't warrant a cross-cutting family.
- Never mix exceptions into a `types.py`.

### `HTTPException` scope

`HTTPException` is only allowed inside `backend/routers/`. Auth, data-access, and agent layers raise `DomainError` subclasses; routers let those propagate to the global handler.

---

## Known gaps

### Content-addressed snapshot cache (wired)

Any clustering operation deterministic given `(parent_snapshot_id, operation,
params, config_hash)` is computed once and reused across conversations:

- `find_cached_snapshot(...)` in `data_access/cluster_snapshots/queries.py`
  returns an existing snapshot when all four inputs match. Uniqueness is
  enforced by a `NULLS NOT DISTINCT` unique index on
  `(parent_id, operation, params, config_hash)`.
- `canonicalize_params(...)` normalises dict ordering and float precision so
  equal-meaning params hash to identical JSONB bytes.
- `create_conversation` leaves `current_cluster_snapshot_id` as NULL; the first
  clustering operation creates the first snapshot and records a
  `conversation_snapshot_refs` row.
- `cluster_snapshots.conversation_id` is gone; the `conversation_snapshot_refs`
  join table records which conversations have touched which snapshots, so
  shared snapshots are not nuked by a single conversation's deletion.

`backend/coordinator/tools/persist.py:persist_and_label` does the cache lookup
before computing; on a hit it skips both clustering and LLM labeling.
