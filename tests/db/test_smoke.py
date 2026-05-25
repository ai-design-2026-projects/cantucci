"""DB smoke test: migrations apply cleanly and are idempotent."""

import psycopg
from pathlib import Path

from db.apply import apply

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"


def test_migrations_applied_and_idempotent(db_url: str) -> None:
    """All migration files are recorded in schema_migrations; re-running applies none.

    Args:
        db_url: Connection URL from the ``db_url`` session fixture.
    """
    second_run = apply(database_url=db_url)
    assert second_run == 0, "Re-applying migrations should be a no-op"

    expected = {f.name for f in _MIGRATIONS_DIR.glob("*.sql")}
    with psycopg.connect(db_url) as conn:
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    recorded = {row[0] for row in rows}
    assert expected == recorded, f"Missing from schema_migrations: {expected - recorded}"
