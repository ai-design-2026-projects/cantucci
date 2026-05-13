"""Tests for backend/api/sessions.py — create_session, append_turn,
snapshot_clusters, write_feedback, mark_converged."""

import uuid

import pytest

from backend.api import runs as api_runs
from backend.api import sessions as api_sessions
from backend.api.types import ClusterSpec


_CONFIG = {"model": {"name": "gpt-4o-mini", "seed": 42, "max_tokens": 512}}


@pytest.fixture()
def run_id(db_url):
    return api_runs.create_run(
        name="sess-test-run",
        condition="component_test",
        config_snapshot=_CONFIG,
        seed=1,
        model_version="gpt-4o-mini",
    )


@pytest.fixture()
def session_id(run_id):
    return api_sessions.create_session(
        run_id=run_id,
        seed=1,
        config_hash="abc12345",
        model_version="gpt-4o-mini",
        max_turns=15,
    )


class TestCreateSession:
    def test_returns_uuid(self, db_url, run_id):
        sid = api_sessions.create_session(
            run_id=run_id,
            seed=42,
            config_hash="abc12345",
            model_version="gpt-4o-mini",
        )
        assert isinstance(sid, uuid.UUID)

    def test_different_calls_give_different_ids(self, db_url, run_id):
        sid1 = api_sessions.create_session(
            run_id=run_id, seed=1, config_hash="aaa", model_version="m"
        )
        sid2 = api_sessions.create_session(
            run_id=run_id, seed=2, config_hash="bbb", model_version="m"
        )
        assert sid1 != sid2


class TestAppendTurn:
    def test_returns_uuid(self, db_url, session_id):
        tid = api_sessions.append_turn(
            session_id=session_id,
            turn_number=1,
            user_message="I like sci-fi",
            assistant_message="Here are some clusters",
            step_type="show",
            converged=False,
        )
        assert isinstance(tid, uuid.UUID)

    def test_pre_allocated_turn_id_preserved(self, db_url, session_id):
        pre = uuid.uuid4()
        returned = api_sessions.append_turn(
            session_id=session_id,
            turn_number=1,
            user_message="test",
            assistant_message=None,
            step_type="ask",
            converged=False,
            turn_id=pre,
        )
        assert returned == pre


class TestSnapshotClusters:
    def test_inserts_clusters_and_assignments(self, db_url, db_conn, session_id):
        from backend.api.db import transaction

        # Seed movie rows so the FK on cluster_assignments is satisfied.
        zero_vec = "[" + ",".join(["0"] * 384) + "]"
        with transaction() as conn:
            for mid, title in [(101, "Test Movie A"), (102, "Test Movie B")]:
                conn.execute(
                    "INSERT INTO movies (id, title, embedding) "
                    "VALUES (%s, %s, %s::vector) ON CONFLICT DO NOTHING",
                    (mid, title, zero_vec),
                )

        turn_id = api_sessions.append_turn(
            session_id=session_id,
            turn_number=1,
            user_message="q",
            assistant_message="a",
            step_type="show",
            converged=False,
        )
        specs = [
            ClusterSpec(
                name="Sci-Fi",
                description="Space operas",
                level=0,
                centroid=None,
                parent_cluster_id=None,
                assignments=[(101, 0.9, False), (102, 0.5, False)],
            ),
            ClusterSpec(
                name="Drama",
                description="Emotional films",
                level=0,
                centroid=None,
                parent_cluster_id=None,
                assignments=[],
            ),
        ]
        cluster_ids = api_sessions.snapshot_clusters(session_id, turn_id, specs)
        assert len(cluster_ids) == 2
        assert all(isinstance(cid, uuid.UUID) for cid in cluster_ids)

    def test_empty_cluster_list_is_noop(self, db_url, session_id):
        turn_id = api_sessions.append_turn(
            session_id=session_id,
            turn_number=1,
            user_message="q",
            assistant_message="a",
            step_type="ask",
            converged=False,
        )
        result = api_sessions.snapshot_clusters(session_id, turn_id, [])
        assert result == []


class TestWriteFeedback:
    def test_returns_uuid(self, db_url, session_id):
        turn_id = api_sessions.append_turn(
            session_id=session_id,
            turn_number=1,
            user_message="love it",
            assistant_message="ok",
            step_type="show",
            converged=False,
        )
        fid = api_sessions.write_feedback(
            session_id=session_id,
            turn_id=turn_id,
            feedback_level="global",
            feedback_type="constraint",
            content="love it",
        )
        assert isinstance(fid, uuid.UUID)

    def test_with_target_id(self, db_url, session_id):
        turn_id = api_sessions.append_turn(
            session_id=session_id,
            turn_number=1,
            user_message="yes",
            assistant_message="ok",
            step_type="ask",
            converged=False,
        )
        cluster_target = str(uuid.uuid4())
        fid = api_sessions.write_feedback(
            session_id=session_id,
            turn_id=turn_id,
            feedback_level="cluster",
            feedback_type="accept",
            content="yes",
            target_id=cluster_target,
        )
        assert isinstance(fid, uuid.UUID)


class TestMarkConverged:
    def test_updates_status_and_profile(self, db_url, session_id):
        from backend.api.db import transaction
        api_sessions.mark_converged(
            session_id=session_id,
            preference_profile={"genres": ["Sci-Fi"], "era": "1980s"},
        )
        with transaction() as conn:
            row = conn.execute(
                "SELECT status, preference_profile FROM sessions WHERE id = %s",
                (session_id,),
            ).fetchone()
        assert row[0] == "converged"
        assert row[1]["genres"] == ["Sci-Fi"]
