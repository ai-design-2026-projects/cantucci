"""Tests for backend/api/runs.py — create_run, finalize_run, get_run."""

import pytest

from backend.api import runs as api_runs


_CONFIG = {"model": {"name": "gpt-4o-mini", "seed": 42, "max_tokens": 512}}


class TestCreateRun:
    def test_returns_uuid(self, db_url):
        from uuid import UUID
        run_id = api_runs.create_run(
            name="test-run",
            condition="baseline",
            config_snapshot=_CONFIG,
            seed=1,
            model_version="gpt-4o-mini",
        )
        assert isinstance(run_id, UUID)

    def test_get_run_returns_matching_row(self, db_url):
        run_id = api_runs.create_run(
            name="my-run",
            condition="baseline",
            config_snapshot=_CONFIG,
            seed=99,
            model_version="gpt-4o-mini",
            notes="unit test",
        )
        run = api_runs.get_run(run_id)
        assert run.id == run_id
        assert run.name == "my-run"
        assert run.condition == "baseline"
        assert run.seed == 99
        assert run.status == "running"
        assert run.notes == "unit test"


class TestFinalizeRun:
    def test_status_becomes_completed(self, db_url):
        run_id = api_runs.create_run(
            name="fin-run",
            condition="baseline",
            config_snapshot=_CONFIG,
            seed=1,
            model_version="gpt-4o-mini",
        )
        api_runs.finalize_run(run_id, status="completed")
        run = api_runs.get_run(run_id)
        assert run.status == "completed"

    def test_status_becomes_aborted(self, db_url):
        run_id = api_runs.create_run(
            name="abort-run",
            condition="baseline",
            config_snapshot=_CONFIG,
            seed=2,
            model_version="gpt-4o-mini",
        )
        api_runs.finalize_run(run_id, status="aborted")
        assert api_runs.get_run(run_id).status == "aborted"


class TestGetRunNotFound:
    def test_raises_value_error(self, db_url):
        from uuid import uuid4
        with pytest.raises(ValueError):
            api_runs.get_run(uuid4())


class TestListRuns:
    def test_returns_list(self, db_url):
        api_runs.create_run(
            name="list-run",
            condition="baseline",
            config_snapshot=_CONFIG,
            seed=1,
            model_version="gpt-4o-mini",
        )
        runs = api_runs.list_runs()
        assert isinstance(runs, list)
        assert len(runs) >= 1

    def test_filter_by_condition(self, db_url):
        api_runs.create_run(
            name="filter-run",
            condition="component_test",
            config_snapshot=_CONFIG,
            seed=1,
            model_version="gpt-4o-mini",
        )
        runs = api_runs.list_runs(condition="component_test")
        assert all(r.condition == "component_test" for r in runs)
