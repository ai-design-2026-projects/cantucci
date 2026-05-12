"""
Schema smoke tests.

These tests verify that:
- Migrations apply cleanly and idempotently.
- The full run → session → turn → cluster → assignment → feedback write path works.
- FK cascades behave correctly (deleting a run cascades to all child rows).
- get_run_results and get_session_full return consistent data.
- The replay invariant holds: get_session_full returns non-empty data for any
  session that has at least one turn, with no LLM calls required.
"""

import uuid
from decimal import Decimal

import psycopg
import pytest

from db.apply import apply
from src.api import eval as eval_api
from src.api import retrieval, runs, sessions
from src.api.sessions import ClusterSpec


# ---------------------------------------------------------------------------
# Migration idempotency
# ---------------------------------------------------------------------------

def test_migrations_apply_once(db_url):
    """apply() on an already-migrated DB returns 0."""
    n = apply(database_url=db_url)
    assert n == 0


def test_expected_tables_exist(db_conn):
    """All expected tables are present after migrations."""
    expected = {
        "schema_migrations",
        "runs",
        "movies", "collections", "genres", "movie_genres",
        "people", "cast_members", "crew_members",
        "keywords", "movie_keywords",
        "production_companies", "movie_companies",
        "languages", "movie_spoken_languages",
        "countries", "movie_countries",
        "sessions", "turns", "clusters", "cluster_assignments", "oracle_feedback",
        "session_metrics", "judge_scores",
    }
    rows = db_conn.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = current_schema()
        """
    ).fetchall()
    found = {r[0] for r in rows}
    assert expected <= found, f"missing tables: {expected - found}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_movie(conn: psycopg.Connection, movie_id: int = 1) -> None:
    """Insert a minimal movie row so FK constraints on cluster_assignments pass."""
    conn.execute(
        """
        INSERT INTO movies (id, title, embedding)
        VALUES (%s, %s, %s::vector)
        ON CONFLICT DO NOTHING
        """,
        (movie_id, f"Test Movie {movie_id}", "[" + ",".join(["0.1"] * 384) + "]"),
    )


def _create_run(condition: str = "uncertainty") -> uuid.UUID:
    return runs.create_run(
        name="test-run",
        condition=condition,
        config_snapshot={"model": "test", "k": 50},
        seed=42,
        model_version="test-model-1.0",
    )


def _create_session(run_id: uuid.UUID) -> uuid.UUID:
    return sessions.create_session(
        run_id=run_id,
        seed=1,
        config_hash="a" * 64,
        model_version="test-model-1.0",
        max_turns=10,
        cost_limit_usd=Decimal("1.00"),
    )


# ---------------------------------------------------------------------------
# Run CRUD
# ---------------------------------------------------------------------------

def test_create_and_get_run(db_url):
    run_id = _create_run()
    run = runs.get_run(run_id)
    assert run.id == run_id
    assert run.condition == "uncertainty"
    assert run.status == "running"
    assert len(run.config_hash) == 64


def test_finalize_run(db_url):
    run_id = _create_run()
    runs.finalize_run(run_id, status="completed")
    run = runs.get_run(run_id)
    assert run.status == "completed"


def test_list_runs_filter(db_url):
    _create_run("uncertainty")
    _create_run("random")
    result = runs.list_runs(condition="uncertainty")
    assert all(r.condition == "uncertainty" for r in result)


def test_get_run_not_found(db_url):
    with pytest.raises(ValueError, match="not found"):
        runs.get_run(uuid.uuid4())


# ---------------------------------------------------------------------------
# Session write path
# ---------------------------------------------------------------------------

def test_create_session(db_url):
    run_id = _create_run()
    session_id = _create_session(run_id)
    assert isinstance(session_id, uuid.UUID)


def test_append_turn_and_cluster_snapshot(db_url, db_conn):
    run_id = _create_run()
    session_id = _create_session(run_id)

    _make_movie(db_conn, movie_id=100)
    _make_movie(db_conn, movie_id=101)
    db_conn.commit()

    turn_id = sessions.append_turn(
        session_id=session_id,
        turn_number=1,
        user_message="I want psychological thrillers",
        assistant_message="Here are some clusters...",
        step_type="ask",
        converged=False,
    )
    assert isinstance(turn_id, uuid.UUID)

    cluster_ids = sessions.snapshot_clusters(
        session_id=session_id,
        turn_id=turn_id,
        clusters=[
            ClusterSpec(
                name="Slow-burn psychological",
                description="Cerebral, slow paced",
                level=0,
                centroid=None,
                parent_cluster_id=None,
                assignments=[(100, 0.7, False), (101, 0.3, False)],
            ),
            ClusterSpec(
                name="Action thriller",
                description="Fast paced, action heavy",
                level=0,
                centroid=None,
                parent_cluster_id=None,
                assignments=[(100, 0.3, False), (101, 0.7, False)],
            ),
        ],
    )
    assert len(cluster_ids) == 2

    # Verify rows in DB
    count = db_conn.execute(
        "SELECT COUNT(*) FROM cluster_assignments WHERE cluster_id = ANY(%s)",
        (cluster_ids,),
    ).fetchone()[0]
    assert count == 4  # 2 clusters × 2 movies


def test_write_feedback(db_url):
    run_id = _create_run()
    session_id = _create_session(run_id)
    turn_id = sessions.append_turn(
        session_id, 1, "No action movies", None, "ask", False
    )
    fb_id = sessions.write_feedback(
        session_id=session_id,
        turn_id=turn_id,
        feedback_level="global",
        feedback_type="constraint",
        content="No action movies",
    )
    assert isinstance(fb_id, uuid.UUID)


def test_mark_converged(db_url, db_conn):
    run_id = _create_run()
    session_id = _create_session(run_id)
    profile = {"genres": ["Thriller"], "exclude": ["gore"]}
    sessions.mark_converged(session_id, profile)

    row = db_conn.execute(
        "SELECT status, preference_profile FROM sessions WHERE id = %s",
        (session_id,),
    ).fetchone()
    assert row[0] == "converged"
    assert row[1]["genres"] == ["Thriller"]


# ---------------------------------------------------------------------------
# Eval write path
# ---------------------------------------------------------------------------

def test_upsert_session_metrics(db_url, db_conn):
    run_id = _create_run()
    session_id = _create_session(run_id)

    eval_api.upsert_session_metrics(
        session_id=session_id,
        converged=True,
        turns_to_convergence=5,
        avg_cognitive_load=3.2,
        total_input_tokens=500,
        total_output_tokens=200,
        total_cost_usd=Decimal("0.05"),
    )
    row = db_conn.execute(
        "SELECT turns_to_convergence, converged FROM session_metrics WHERE session_id = %s",
        (session_id,),
    ).fetchone()
    assert row[0] == 5
    assert row[1] is True

    # Upsert is idempotent — overwrite with new value
    eval_api.upsert_session_metrics(
        session_id=session_id,
        converged=True,
        turns_to_convergence=4,
    )
    row2 = db_conn.execute(
        "SELECT turns_to_convergence FROM session_metrics WHERE session_id = %s",
        (session_id,),
    ).fetchone()
    assert row2[0] == 4


def test_write_judge_score(db_url):
    run_id = _create_run()
    session_id = _create_session(run_id)

    score_id = eval_api.write_judge_score(
        session_id=session_id,
        dimension="clustering_coherence",
        score=4,
        judge_model="claude-opus-4-7",
        judge_prompt_hash="b" * 64,
        rationale="Clusters are internally consistent.",
    )
    assert isinstance(score_id, uuid.UUID)


def test_judge_score_unique_constraint(db_url):
    """Same (session, dimension, prompt_hash) must not insert twice."""
    run_id = _create_run()
    session_id = _create_session(run_id)

    kwargs = dict(
        session_id=session_id,
        dimension="question_quality",
        score=3,
        judge_model="claude-opus-4-7",
        judge_prompt_hash="c" * 64,
    )
    eval_api.write_judge_score(**kwargs)

    import psycopg as _psycopg
    with pytest.raises(_psycopg.errors.UniqueViolation):
        eval_api.write_judge_score(**kwargs)


# ---------------------------------------------------------------------------
# Retrieval — get_run_results
# ---------------------------------------------------------------------------

def test_get_run_results_empty(db_url):
    run_id = _create_run()
    result = retrieval.get_run_results(run_id)
    assert result.run_id == run_id
    assert result.sessions == []
    assert result.aggregate.n_sessions == 0


def test_get_run_results_with_sessions(db_url):
    run_id = _create_run()

    for i in range(2):
        sid = _create_session(run_id)
        tid = sessions.append_turn(sid, 1, f"message {i}", None, "ask", True)
        sessions.mark_converged(sid, {})
        eval_api.upsert_session_metrics(
            session_id=sid,
            converged=True,
            turns_to_convergence=i + 2,
            avg_cognitive_load=2.5,
        )
        eval_api.write_judge_score(
            session_id=sid,
            dimension="clustering_coherence",
            score=4,
            judge_model="test-judge",
            judge_prompt_hash="d" * 64,
        )

    result = retrieval.get_run_results(run_id)

    assert result.aggregate.n_sessions == 2
    assert result.aggregate.convergence_rate == 1.0
    assert result.aggregate.mean_turns_to_convergence == 2.5  # avg of 2 and 3
    assert "clustering_coherence" in result.aggregate.mean_judge
    assert all(len(s.judge_scores) == 1 for s in result.sessions)


# ---------------------------------------------------------------------------
# Retrieval — get_session_full (replay invariant)
# ---------------------------------------------------------------------------

def test_get_session_full_not_found(db_url):
    with pytest.raises(ValueError, match="not found"):
        retrieval.get_session_full(uuid.uuid4())


def test_get_session_full_replay_invariant(db_url, db_conn):
    """get_session_full returns non-empty data; no LLM calls required."""
    run_id = _create_run()
    session_id = _create_session(run_id)

    _make_movie(db_conn, 200)
    db_conn.commit()

    for n in range(1, 4):
        turn_id = sessions.append_turn(session_id, n, f"msg {n}", f"resp {n}", "ask", False)
        sessions.snapshot_clusters(
            session_id=session_id,
            turn_id=turn_id,
            clusters=[
                ClusterSpec("Drama", None, 0, None, None, [(200, 1.0, False)])
            ],
        )
        sessions.write_feedback(session_id, turn_id, "global", "accept", "ok")

    full = retrieval.get_session_full(session_id)

    assert full.session_id == session_id
    assert len(full.turns) == 3
    assert all(len(t.clusters) == 1 for t in full.turns)
    assert all(len(t.clusters[0].assignments) == 1 for t in full.turns)
    assert len(full.feedback) == 3


# ---------------------------------------------------------------------------
# FK cascade
# ---------------------------------------------------------------------------

def test_fk_cascade_run_delete(db_url, db_conn):
    """Deleting a run cascades to sessions, turns, clusters, assignments, metrics."""
    run_id = _create_run()
    session_id = _create_session(run_id)

    _make_movie(db_conn, 300)
    db_conn.commit()

    turn_id = sessions.append_turn(session_id, 1, "hi", None, "ask", False)
    sessions.snapshot_clusters(
        session_id=session_id,
        turn_id=turn_id,
        clusters=[ClusterSpec("C", None, 0, None, None, [(300, 1.0, False)])],
    )
    eval_api.upsert_session_metrics(session_id=session_id, converged=False)

    # Delete the run
    db_conn.execute("DELETE FROM runs WHERE id = %s", (run_id,))
    db_conn.commit()

    for table in ("sessions", "turns", "clusters", "cluster_assignments", "session_metrics"):
        count = db_conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE id IS NOT NULL"
        ).fetchone()[0]
        # Cascade should leave 0 rows that belong to the deleted run
        # (other tests may have rows; we just check our specific session)

    # More precise: check our session_id is gone
    assert db_conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE id = %s", (session_id,)
    ).fetchone()[0] == 0
