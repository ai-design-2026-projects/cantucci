# Public API and Internal Interfaces

Named contracts between modules: inputs, outputs, error cases. These are the
handoffs that ablation and multi-person work depend on. Each section covers one
agent or layer.

---

## Retrieval System

The Retrieval System converts an oracle query into enriched film candidates.
SQL lives in `backend/api/movies.py`; the agent entry-point is
`backend/retrieval/agent.py`; tool implementations are in
`backend/retrieval/tools/`.

### `retrieve` — agent entry-point

```
backend.retrieval.agent.retrieve(
    *,
    query: str,
    k: int,
    active_constraints: dict | None = None,
) -> RetrievalResult
```

**Input**
| Parameter | Type | Description |
|---|---|---|
| `query` | `str` | Natural-language oracle preference string (non-empty). |
| `k` | `int` | Maximum candidates to return (positive integer). |
| `active_constraints` | `dict \| None` | Hard constraints from oracle state. Accepted but not yet applied (v1 no-op; logs WARNING). |

**Output** — `RetrievalResult` (`backend/models/movies.py`)
| Field | Type | Description |
|---|---|---|
| `query` | `str` | Echo of the input query. |
| `k` | `int` | Echo of the input k. |
| `candidates` | `list[MovieMetadata]` | Films in descending similarity order. |
| `scores` | `dict[int, float]` | `movie_id → cosine similarity` for every candidate. |

**Error cases**
| Condition | Exception |
|---|---|
| `query` is empty or whitespace | `ValueError("query must be a non-empty string")` |
| `k ≤ 0` | `ValueError("k must be positive, got {k}")` |
| DB unreachable | `psycopg.OperationalError` (propagates from `tx()`) |

---

### `vector_search` — tool

```
backend.api.movies.vector_search(
    embedding: list[float] | np.ndarray,
    k: int,
) -> list[MovieHit]
```

Queries the `movies` table using pgvector cosine distance (`<=>` operator).
Returns similarity = `1 − cosine_distance` so the list is descending by relevance.

**Input**
| Parameter | Type | Description |
|---|---|---|
| `embedding` | `list[float] \| ndarray` | 384-dim query vector (must match `movies.embedding` dimension). |
| `k` | `int` | Maximum results. |

**Output** — `list[MovieHit]`
| Field | Type | Description |
|---|---|---|
| `movie_id` | `int` | TMDB integer ID. |
| `title` | `str` | Film title. |
| `score` | `float` | Cosine similarity in approximately [0, 1]. |

**Error cases**
| Condition | Exception |
|---|---|
| `k ≤ 0` | `ValueError("k must be positive, got {k}")` |

---

### `fetch_metadata` — tool (Librarian)

```
backend.api.movies.fetch_metadata(
    movie_ids: list[int],
) -> list[MovieMetadata]
```

Enriches a list of TMDB IDs with synopsis, genre names, and director.
Joins `movies ← movie_genres → genres` and `crew_members (job='Director')`.
Return order matches the input `movie_ids` order; missing IDs are silently
dropped (the catalogue is authoritative).

**Input**
| Parameter | Type | Description |
|---|---|---|
| `movie_ids` | `list[int]` | TMDB IDs returned by `vector_search`. |

**Output** — `list[MovieMetadata]`
| Field | Type | Description |
|---|---|---|
| `movie_id` | `int` | TMDB integer ID. |
| `title` | `str` | Film title. |
| `overview` | `str \| None` | Synopsis. |
| `tagline` | `str \| None` | Tagline. |
| `release_year` | `int \| None` | Year extracted from `release_date`. |
| `genres` | `list[str]` | Genre names; empty list if none. |
| `director` | `str \| None` | First director found; `None` if no crew record. |

**Error cases**
| Condition | Behaviour |
|---|---|
| Empty `movie_ids` | Returns `[]` immediately (no DB round-trip). |
| ID not in catalogue | Silently omitted from result. |
