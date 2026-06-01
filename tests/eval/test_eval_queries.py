"""Direct round-trip tests for backend/data_access/eval/queries.py.

Each test seeds the data it needs via the query write-path helpers, exercises
one or more read-path functions, and asserts the returned dataclass fields.
The ``_clean_db`` autouse fixture (from conftest.py) resets eval tables before
each test, so tests are independent.
"""
import uuid

import pytest

from backend.data_access.eval.queries import (
    count_runs_by_name,
    create_eval_session,
    create_ground_truth,
    create_persona,
    create_run,
    get_conversation_metrics,
    get_eval_session,
    get_eval_session_by_conversation,
    get_ground_truth_by_id,
    get_ground_truth_by_slug,
    get_judge_scores,
    get_persona_by_id,
    get_persona_by_slug,
    get_run,
    get_run_aggregate,
    get_run_by_name,
    insert_judge_score,
    insert_turn_intent,
    list_eval_sessions_for_run,
    list_ground_truths,
    list_personas,
    list_runs,
    list_turn_intents,
    upsert_conversation_metrics,
)
from tests.conftest import (
    seed_conversation,
    seed_eval_session,
    seed_ground_truth,
    seed_persona,
    seed_run,
)


class TestRunCRUD:
    """create_run / get_run / get_run_by_name / count_runs_by_name / list_runs"""

    def test_create_and_get_run(self, db_url: str) -> None:
        """A created run can be retrieved by its UUID."""
        run_id = seed_run(name="r1", seed=1)
        row = get_run(run_id)
        assert row is not None
        assert row.run_id == run_id
        assert row.name == "r1"
        assert row.seed == 1
        assert row.condition == "conversational"

    def test_get_run_not_found(self, db_url: str) -> None:
        """get_run returns None for an unknown UUID."""
        assert get_run(uuid.uuid4()) is None

    def test_get_run_by_name(self, db_url: str) -> None:
        """get_run_by_name returns the most recently started run with that name."""
        seed_run(name="shared", seed=10)
        run_id = seed_run(name="shared", seed=20)
        row = get_run_by_name("shared")
        assert row is not None
        assert row.run_id == run_id

    def test_get_run_by_name_not_found(self, db_url: str) -> None:
        """get_run_by_name returns None when no run matches."""
        assert get_run_by_name("nonexistent") is None

    def test_count_runs_by_name(self, db_url: str) -> None:
        """count_runs_by_name returns the exact count of matching names."""
        seed_run(name="counted", seed=1)
        seed_run(name="counted", seed=2)
        seed_run(name="other", seed=3)
        assert count_runs_by_name("counted") == 2
        assert count_runs_by_name("other") == 1
        assert count_runs_by_name("missing") == 0

    def test_list_runs_empty(self, db_url: str) -> None:
        """list_runs returns an empty list when no runs exist."""
        assert list_runs() == []

    def test_list_runs_ordered_newest_first(self, db_url: str) -> None:
        """list_runs returns runs ordered by started_at descending."""
        r1 = seed_run(name="first", seed=1)
        r2 = seed_run(name="second", seed=2)
        rows = list_runs()
        assert len(rows) == 2
        assert rows[0].run_id == r2
        assert rows[1].run_id == r1

    def test_list_runs_limit_offset(self, db_url: str) -> None:
        """list_runs respects limit and offset."""
        for i in range(5):
            seed_run(name=f"run-{i}", seed=i)
        assert len(list_runs(limit=3, offset=0)) == 3
        assert len(list_runs(limit=3, offset=3)) == 2


class TestPersonaCRUD:
    """create_persona / get_persona_by_id / get_persona_by_slug / list_personas"""

    def test_create_and_get_persona(self, db_url: str) -> None:
        """A created persona can be retrieved by its UUID."""
        persona_id = seed_persona(slug="p1")
        row = get_persona_by_id(persona_id)
        assert row is not None
        assert row.id == persona_id
        assert row.slug == "p1"

    def test_get_persona_not_found(self, db_url: str) -> None:
        """get_persona_by_id returns None for an unknown UUID."""
        assert get_persona_by_id(uuid.uuid4()) is None

    def test_get_persona_by_slug(self, db_url: str) -> None:
        """get_persona_by_slug returns the persona with the matching slug."""
        persona_id = seed_persona(slug="findme")
        row = get_persona_by_slug("findme")
        assert row is not None
        assert row.id == persona_id

    def test_get_persona_by_slug_not_found(self, db_url: str) -> None:
        """get_persona_by_slug returns None when the slug does not exist."""
        assert get_persona_by_slug("nope") is None

    def test_list_personas_empty(self, db_url: str) -> None:
        """list_personas returns an empty list when no personas exist."""
        assert list_personas() == []

    def test_list_personas_returns_all(self, db_url: str) -> None:
        """list_personas returns every seeded persona."""
        seed_persona("pa")
        seed_persona("pb")
        rows = list_personas()
        assert len(rows) == 2
        slugs = {r.slug for r in rows}
        assert slugs == {"pa", "pb"}


class TestGroundTruthCRUD:
    """create_ground_truth / get_ground_truth_by_id / get_ground_truth_by_slug / list_ground_truths"""

    def test_create_and_get_ground_truth(self, db_url: str) -> None:
        """A created ground-truth can be retrieved by its UUID."""
        gt_id = seed_ground_truth(slug="gt1")
        row = get_ground_truth_by_id(gt_id)
        assert row is not None
        assert row.id == gt_id
        assert row.slug == "gt1"
        assert row.version == 1

    def test_get_ground_truth_not_found(self, db_url: str) -> None:
        """get_ground_truth_by_id returns None for an unknown UUID."""
        assert get_ground_truth_by_id(uuid.uuid4()) is None

    def test_get_ground_truth_by_slug(self, db_url: str) -> None:
        """get_ground_truth_by_slug returns the row with the matching slug."""
        gt_id = seed_ground_truth(slug="findgt")
        row = get_ground_truth_by_slug("findgt")
        assert row is not None
        assert row.id == gt_id

    def test_get_ground_truth_by_slug_not_found(self, db_url: str) -> None:
        """get_ground_truth_by_slug returns None when the slug does not exist."""
        assert get_ground_truth_by_slug("nope") is None

    def test_list_ground_truths_empty(self, db_url: str) -> None:
        """list_ground_truths returns an empty list when no rows exist."""
        assert list_ground_truths() == []

    def test_list_ground_truths_returns_all(self, db_url: str) -> None:
        """list_ground_truths returns every seeded row."""
        seed_ground_truth("g1")
        seed_ground_truth("g2")
        rows = list_ground_truths()
        assert len(rows) == 2


class TestEvalSessionCRUD:
    """create_eval_session / get_eval_session / list_eval_sessions_for_run / get_eval_session_by_conversation"""

    def test_create_and_get_session(self, db_url: str) -> None:
        """A created eval session can be retrieved by its UUID."""
        run_id = seed_run()
        conv_id = seed_conversation()
        session_id = seed_eval_session(run_id=run_id, conversation_id=conv_id)
        row = get_eval_session(session_id)
        assert row is not None
        assert row.id == session_id
        assert row.run_id == run_id
        assert row.conversation_id == conv_id
        assert row.status == "active"

    def test_get_session_not_found(self, db_url: str) -> None:
        """get_eval_session returns None for an unknown UUID."""
        assert get_eval_session(uuid.uuid4()) is None

    def test_session_with_persona_and_gt(self, db_url: str) -> None:
        """A session's persona_id and ground_truth_id are stored and retrieved."""
        run_id = seed_run()
        conv_id = seed_conversation()
        persona_id = seed_persona()
        gt_id = seed_ground_truth()
        session_id = seed_eval_session(
            run_id=run_id,
            conversation_id=conv_id,
            persona_id=persona_id,
            ground_truth_id=gt_id,
        )
        row = get_eval_session(session_id)
        assert row is not None
        assert row.persona_id == persona_id
        assert row.ground_truth_id == gt_id

    def test_list_sessions_for_run(self, db_url: str) -> None:
        """list_eval_sessions_for_run returns all sessions for the given run."""
        run_id = seed_run()
        other_run_id = seed_run(name="other")
        conv1 = seed_conversation()
        conv2 = seed_conversation()
        conv3 = seed_conversation()
        seed_eval_session(run_id=run_id, conversation_id=conv1)
        seed_eval_session(run_id=run_id, conversation_id=conv2)
        seed_eval_session(run_id=other_run_id, conversation_id=conv3)
        rows = list_eval_sessions_for_run(run_id)
        assert len(rows) == 2
        conv_ids = {r.conversation_id for r in rows}
        assert conv_ids == {conv1, conv2}

    def test_list_sessions_for_unknown_run(self, db_url: str) -> None:
        """list_eval_sessions_for_run returns empty list for a non-existent run."""
        assert list_eval_sessions_for_run(uuid.uuid4()) == []

    def test_get_session_by_conversation(self, db_url: str) -> None:
        """get_eval_session_by_conversation returns the session linked to a conversation."""
        run_id = seed_run()
        conv_id = seed_conversation()
        session_id = seed_eval_session(run_id=run_id, conversation_id=conv_id)
        row = get_eval_session_by_conversation(conv_id)
        assert row is not None
        assert row.id == session_id

    def test_get_session_by_conversation_not_found(self, db_url: str) -> None:
        """get_eval_session_by_conversation returns None for an unlinked conversation."""
        assert get_eval_session_by_conversation(uuid.uuid4()) is None


class TestTurnIntents:
    """insert_turn_intent / list_turn_intents"""

    def test_insert_and_list_turn_intents(self, db_url: str) -> None:
        """Inserted turn intents are returned by list_turn_intents, ordered by turn_number."""
        conv_id = seed_conversation()
        insert_turn_intent(
            conversation_id=conv_id,
            turn_number=1,
            mode="partition_by",
            confidence=0.9,
            raw_intent={"mode": "partition_by"},
            concept="genre",
        )
        insert_turn_intent(
            conversation_id=conv_id,
            turn_number=2,
            mode="split_cluster",
            confidence=0.8,
            raw_intent={"mode": "split_cluster"},
        )
        rows = list_turn_intents(conv_id)
        assert len(rows) == 2
        assert rows[0].turn_number == 1
        assert rows[0].mode == "partition_by"
        assert rows[0].concept == "genre"
        assert rows[1].turn_number == 2

    def test_list_turn_intents_empty(self, db_url: str) -> None:
        """list_turn_intents returns an empty list for a conversation with no intents."""
        conv_id = seed_conversation()
        assert list_turn_intents(conv_id) == []

    def test_duplicate_intent_is_skipped(self, db_url: str) -> None:
        """Inserting the same (conversation_id, turn_number, mode) twice is idempotent."""
        conv_id = seed_conversation()
        insert_turn_intent(conv_id, 1, "small_talk", 0.5, {})
        insert_turn_intent(conv_id, 1, "small_talk", 0.9, {})
        assert len(list_turn_intents(conv_id)) == 1


class TestConversationMetrics:
    """upsert_conversation_metrics / get_conversation_metrics"""

    def test_upsert_and_get_metrics(self, db_url: str) -> None:
        """Upserted metrics can be retrieved immediately."""
        conv_id = seed_conversation()
        upsert_conversation_metrics(
            conversation_id=conv_id,
            final_num_clusters=5,
            clarifier_trigger_rate=0.2,
            num_turns=10,
            num_operations=7,
            total_cost_usd=0.05,
        )
        row = get_conversation_metrics(conv_id)
        assert row is not None
        assert row.final_num_clusters == 5
        assert row.num_turns == 10
        assert row.total_cost_usd == pytest.approx(0.05, abs=1e-4)

    def test_upsert_overwrites_previous(self, db_url: str) -> None:
        """A second upsert replaces the previous metrics for the same conversation."""
        conv_id = seed_conversation()
        upsert_conversation_metrics(conv_id, 3, None, 5, 3, 0.01)
        upsert_conversation_metrics(conv_id, 7, 0.4, 12, 9, 0.08)
        row = get_conversation_metrics(conv_id)
        assert row is not None
        assert row.final_num_clusters == 7
        assert row.num_turns == 12

    def test_get_metrics_not_found(self, db_url: str) -> None:
        """get_conversation_metrics returns None for a conversation with no metrics."""
        conv_id = seed_conversation()
        assert get_conversation_metrics(conv_id) is None


class TestJudgeScores:
    """insert_judge_score / get_judge_scores"""

    def test_insert_and_get_judge_scores(self, db_url: str) -> None:
        """Inserted judge scores are returned by get_judge_scores."""
        conv_id = seed_conversation()
        insert_judge_score(
            conversation_id=conv_id,
            dimension="intent_alignment",
            score=4,
            judge_model="gpt-4o",
            judge_prompt_hash="b" * 64,
            rationale="Good alignment.",
        )
        insert_judge_score(
            conversation_id=conv_id,
            dimension="label_accuracy",
            score=3,
            judge_model="gpt-4o",
            judge_prompt_hash="c" * 64,
        )
        scores = get_judge_scores(conv_id)
        assert len(scores) == 2
        dims = {s.dimension for s in scores}
        assert dims == {"intent_alignment", "label_accuracy"}

    def test_get_judge_scores_empty(self, db_url: str) -> None:
        """get_judge_scores returns an empty list for a conversation with no scores."""
        conv_id = seed_conversation()
        assert get_judge_scores(conv_id) == []


class TestGetRunAggregate:
    """get_run_aggregate over a fully-seeded session"""

    def test_run_aggregate_with_session(self, db_url: str) -> None:
        """get_run_aggregate returns the run row and a populated session list."""
        run_id = seed_run(name="agg-run")
        conv_id = seed_conversation()
        session_id = seed_eval_session(run_id=run_id, conversation_id=conv_id)
        upsert_conversation_metrics(conv_id, 4, 0.1, 8, 5, 0.03)
        insert_judge_score(conv_id, "intent_alignment", 5, "gpt-4o", "d" * 64)

        run_row, session_rows = get_run_aggregate(run_id)
        assert run_row is not None
        assert run_row.run_id == run_id
        assert len(session_rows) == 1
        assert session_rows[0].id == session_id
        assert session_rows[0].final_num_clusters == 4

    def test_run_aggregate_unknown_run(self, db_url: str) -> None:
        """get_run_aggregate returns (None, []) for an unknown run UUID."""
        run_row, session_rows = get_run_aggregate(uuid.uuid4())
        assert run_row is None
        assert session_rows == []

    def test_run_aggregate_empty_run(self, db_url: str) -> None:
        """get_run_aggregate returns the run row with an empty session list when no sessions exist."""
        run_id = seed_run(name="empty-run")
        run_row, session_rows = get_run_aggregate(run_id)
        assert run_row is not None
        assert session_rows == []
