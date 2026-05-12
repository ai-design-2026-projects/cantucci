"""
Apply all pending SQL migrations from db/migrations/ in lexicographic order.

Usage:
    python -m db.apply

Each migration file is run inside a single transaction. If it succeeds, the
version name is written to schema_migrations so the file is never re-applied.
Any SQL error raises immediately — no silent partial commits.
"""

import logging
import sys
from pathlib import Path

import psycopg

# Allow invocation as `python -m db.apply` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import database_url as get_database_url  # noqa: E402
from src.logging_setup import configure_logging  # noqa: E402

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _ensure_migrations_table(conn: psycopg.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    TEXT        PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def _applied_versions(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def apply(database_url: str | None = None) -> int:
    """Apply all pending migrations. Returns the number of migrations applied."""
    url = database_url or get_database_url()

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        raise RuntimeError(f"No migration files found in {MIGRATIONS_DIR}")

    applied_count = 0

    with psycopg.connect(url, autocommit=False) as conn:
        _ensure_migrations_table(conn)
        conn.commit()

        already_applied = _applied_versions(conn)

        for path in migration_files:
            version = path.name
            if version in already_applied:
                log.debug("skip %s (already applied)", version)
                continue

            sql = path.read_text()
            log.info("applying %s", version)

            with conn.transaction():
                conn.execute(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)", (version,)
                )

            applied_count += 1
            log.info("applied %s", version)

    return applied_count


def main() -> None:
    configure_logging()
    try:
        n = apply()
    except KeyError:
        log.critical("DATABASE_URL environment variable is not set")
        sys.exit(1)

    if n == 0:
        log.info("no pending migrations")
    else:
        log.info("applied %d migration(s)", n)


if __name__ == "__main__":
    main()
