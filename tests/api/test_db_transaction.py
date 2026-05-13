"""Tests for backend/api/db.py — transaction() commit and rollback."""

import psycopg
import pytest

from backend.api.db import transaction


class TestTransactionCommit:
    def test_write_is_visible_after_context_exit(self, db_url):
        with transaction() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS _tx_test (v int)"
            )
            conn.execute("INSERT INTO _tx_test VALUES (42)")

        with transaction() as conn:
            row = conn.execute("SELECT v FROM _tx_test").fetchone()
        assert row is not None and row[0] == 42


class TestTransactionRollback:
    def test_exception_rolls_back_write(self, db_url):
        with transaction() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS _tx_rb_test (v int)")

        try:
            with transaction() as conn:
                conn.execute("INSERT INTO _tx_rb_test VALUES (99)")
                raise RuntimeError("deliberate rollback")
        except RuntimeError:
            pass

        with transaction() as conn:
            count = conn.execute(
                "SELECT count(*) FROM _tx_rb_test"
            ).fetchone()[0]
        assert count == 0
