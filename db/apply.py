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
from pydantic import ValidationError

# Allow invocation as `python -m db.apply` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.settings import MIGRATIONS_DIR, get_env  # noqa: E402
from backend.logging_setup import configure_logging  # noqa: E402

log = logging.getLogger(__name__)


def _ensure_migrations_table(conn: psycopg.Connection) -> None:
    """Create the schema_migrations table if it doesn't exist. This table tracks which migrations have been applied."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    TEXT        PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def _applied_versions(conn: psycopg.Connection) -> set[str]:
    """Fetch the set of already applied migration versions from the database."""
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def apply(database_url: str | None = None) -> int:
    """Apply all pending migrations. Returns the number of migrations applied."""
    url = database_url or get_env().database_url

    # Get all the migration files and sort them lexicographically (respecting the intended order).
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        raise RuntimeError(f"No migration files found in {MIGRATIONS_DIR}")

    applied_count = 0
    with psycopg.connect(url, autocommit=False) as conn:
        # Ensure the schema_migrations table exists
        _ensure_migrations_table(conn)
        conn.commit()

        # Check which migrations have already been applied to avoid re-applying them
        already_applied = _applied_versions(conn)
        for migration_file in migration_files:
            # Check if this migration has already been applied
            version = migration_file.name
            if version in already_applied:
                log.debug("skip %s (already applied)", version)
                continue
            
            # Otherwise, read the SQL and apply the migration inside a transaction
            migration_query = migration_file.read_text()
            log.info("applying %s", version)
            with conn.transaction():
                conn.execute(migration_query)
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)", (version,)
                )
            applied_count += 1
            log.info("applied %s", version)

    return applied_count


def main() -> None:
    configure_logging()
    log.info("applying pending migrations to database at %s", get_env().database_url)

    try:
        applied_migrations = apply()
    except ValidationError:
        log.critical("DATABASE_URL environment variable is not set")
        sys.exit(1)

    if applied_migrations == 0:
        log.info("no pending migrations")
    else:
        log.info("applied %d migration(s)", applied_migrations)


if __name__ == "__main__":
    main()
