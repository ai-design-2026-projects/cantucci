"""Top-level conftest — intentionally minimal.

All shared fixtures live in ``tests/db/test_config.py`` (auto-registered via the
``-p tests.db.test_config`` entry in ``pyproject.toml``). Keeping this file as
a stable touchpoint means any future cross-suite hook can land here without
re-plumbing pytest's plugin loader.
"""
