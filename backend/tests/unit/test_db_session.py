"""Unit tests for database session management.

This module contains tests for the database session management functionality, including:
- Async session generator yielding AsyncSession instances
- Context manager behavior for proper cleanup
- Session independence across multiple calls
- init_db migration behavior for fresh and legacy (untracked) databases
"""

import asyncio
import os
import sqlite3

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.session import _INITIAL_REVISION, get_db, init_db


@pytest.mark.asyncio
async def test_get_db_yields_session():
    """Test that get_db yields an AsyncSession."""
    # GIVEN: The get_db async generator is available
    # WHEN: Iterating over get_db to get a session
    # THEN: An AsyncSession instance is yielded

    async for session in get_db():
        assert isinstance(session, AsyncSession)
        assert session is not None
        break


@pytest.mark.asyncio
async def test_get_db_session_context_manager():
    """Test that get_db works as an async context manager."""
    # GIVEN: The get_db async generator is available
    # WHEN: Using get_db in an async context
    # THEN: Exactly one session is yielded per iteration

    session_count = 0
    async for session in get_db():
        session_count += 1
        assert isinstance(session, AsyncSession)
        break

    assert session_count == 1


@pytest.mark.asyncio
async def test_multiple_get_db_calls_independent():
    """Test that multiple get_db calls yield independent sessions."""
    # GIVEN: The get_db async generator is available
    # WHEN: Calling get_db multiple times
    # THEN: Each call yields a different AsyncSession instance

    sessions = []

    async for session1 in get_db():
        sessions.append(session1)
        break

    async for session2 in get_db():
        sessions.append(session2)
        break

    # Sessions should be different objects
    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]


def _alembic_config():
    """Build the same Alembic config init_db uses."""
    from alembic.config import Config

    import db.session as db_session

    src_dir = os.path.dirname(os.path.dirname(os.path.abspath(db_session.__file__)))
    cfg = Config(os.path.join(src_dir, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(src_dir, "alembic"))
    return cfg


def _head_revision():
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(_alembic_config()).get_current_head()


def _db_revision(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        conn.close()


def _column_names(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_init_db_fresh_database_migrates_to_head(tmp_path, monkeypatch):
    """Test that init_db brings a brand-new database to the head revision."""
    # GIVEN: A database URL pointing at a nonexistent SQLite file
    db_path = tmp_path / "fresh.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")

    # WHEN: Initializing the database
    await init_db()

    # THEN: The database exists, is tracked at head, and has current-schema columns
    assert db_path.exists()
    assert _db_revision(db_path) == _head_revision()
    assert "is_dlc" in _column_names(db_path, "giveaways")


@pytest.mark.asyncio
async def test_init_db_legacy_untracked_database_upgrades_to_head(tmp_path, monkeypatch):
    """Test that an untracked initial-schema database is stamped then upgraded.

    Regression test: init_db used to stamp untracked databases at *head* and
    return, silently skipping every migration after the initial schema.
    """
    # GIVEN: A database at the initial schema revision with no alembic tracking
    db_path = tmp_path / "legacy.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")

    from alembic import command

    # env.py uses asyncio.run(), so alembic commands must run outside this loop
    await asyncio.to_thread(command.upgrade, _alembic_config(), _INITIAL_REVISION)
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE alembic_version")
    conn.commit()
    conn.close()
    assert "is_dlc" not in _column_names(db_path, "giveaways")

    # WHEN: Initializing the database
    await init_db()

    # THEN: The database is upgraded to head with post-initial columns present
    assert _db_revision(db_path) == _head_revision()
    assert "is_dlc" in _column_names(db_path, "giveaways")


@pytest.mark.asyncio
async def test_init_db_tracked_database_applies_pending_migrations(tmp_path, monkeypatch):
    """Test that a tracked database at an older revision is upgraded, not stamped."""
    # GIVEN: A database tracked at the initial revision
    db_path = tmp_path / "tracked.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")

    from alembic import command

    await asyncio.to_thread(command.upgrade, _alembic_config(), _INITIAL_REVISION)
    assert _db_revision(db_path) == _INITIAL_REVISION

    # WHEN: Initializing the database
    await init_db()

    # THEN: Pending migrations are applied up to head
    assert _db_revision(db_path) == _head_revision()
    assert "is_dlc" in _column_names(db_path, "giveaways")


ENDING_SOON_REVISION = "e3a9c7b5d1f4"
ENDING_SOON_COLUMNS = {"ending_soon_priority_enabled", "ending_soon_threshold_minutes"}


@pytest.mark.asyncio
async def test_ending_soon_migration_upgrade_backfills_and_downgrade_drops(tmp_path, monkeypatch):
    """The ending-soon settings revision revises a7d4e8f2c6b1, lies on the
    single head's lineage, backfills an existing settings row with False/60 and downgrades
    cleanly in batch mode."""
    from alembic.script import ScriptDirectory

    from alembic import command

    # GIVEN: A database at the previous head with an existing settings row
    db_path = tmp_path / "ending_soon.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    await asyncio.to_thread(command.upgrade, cfg, "a7d4e8f2c6b1")
    assert ENDING_SOON_COLUMNS.isdisjoint(_column_names(db_path, "settings"))
    conn = sqlite3.connect(db_path)
    row_values = {
        "id": 1, "user_agent": "ua", "safety_check_enabled": 1, "auto_hide_unsafe": 1,
        "autojoin_enabled": 0, "autojoin_start_at": 350, "autojoin_stop_at": 200,
        "autojoin_min_price": 10, "autojoin_min_score": 7, "autojoin_min_reviews": 1000,
        "scan_interval_minutes": 30, "automation_enabled": 0, "max_scan_pages": 3,
        "entry_delay_min": 8, "entry_delay_max": 12,
        "created_at": "2026-01-01 00:00:00", "updated_at": "2026-01-01 00:00:00",
    }
    conn.execute(
        f"INSERT INTO settings ({', '.join(row_values)}) "
        f"VALUES ({', '.join('?' * len(row_values))})",
        tuple(row_values.values()),
    )
    conn.commit()
    conn.close()

    # THEN: the chain is a7d4e8f2c6b1 -> ending-soon, there is a single head,
    # and the ending-soon revision is on its lineage (later revisions may
    # build on top of it without breaking this test)
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1
    lineage = {rev.revision for rev in script.iterate_revisions(heads[0], "base")}
    assert ENDING_SOON_REVISION in lineage
    assert script.get_revision(ENDING_SOON_REVISION).down_revision == "a7d4e8f2c6b1"

    # WHEN: Upgrading to the ending-soon revision
    await asyncio.to_thread(command.upgrade, cfg, ENDING_SOON_REVISION)

    # THEN: Both columns exist and the existing row got the defaults
    assert _db_revision(db_path) == ENDING_SOON_REVISION
    assert ENDING_SOON_COLUMNS <= _column_names(db_path, "settings")
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT ending_soon_priority_enabled, ending_soon_threshold_minutes "
            "FROM settings WHERE id = 1"
        ).fetchone()
    finally:
        conn.close()
    assert row == (0, 60)

    # WHEN: Downgrading back to the previous revision
    await asyncio.to_thread(command.downgrade, cfg, "a7d4e8f2c6b1")

    # THEN: Both columns are gone and the row survives
    assert _db_revision(db_path) == "a7d4e8f2c6b1"
    assert ENDING_SOON_COLUMNS.isdisjoint(_column_names(db_path, "settings"))
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 1
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_ending_soon_migration_round_trip_on_empty_database(tmp_path, monkeypatch):
    """On an empty SQLite database the ending-soon revision upgrades, downgrades
    and re-upgrades cleanly, and the server defaults fill a row inserted
    without the new columns (NOT NULL holds)."""
    from alembic import command

    # GIVEN: A brand-new empty database
    db_path = tmp_path / "ending_soon_empty.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    # WHEN: Upgrading from nothing to the ending-soon revision, then back
    await asyncio.to_thread(command.upgrade, cfg, ENDING_SOON_REVISION)
    assert _db_revision(db_path) == ENDING_SOON_REVISION
    assert ENDING_SOON_COLUMNS <= _column_names(db_path, "settings")

    await asyncio.to_thread(command.downgrade, cfg, "a7d4e8f2c6b1")
    assert _db_revision(db_path) == "a7d4e8f2c6b1"
    assert ENDING_SOON_COLUMNS.isdisjoint(_column_names(db_path, "settings"))

    # AND: Re-upgrading to head works (downgrade left no residue)
    await asyncio.to_thread(command.upgrade, cfg, "head")
    assert _db_revision(db_path) == _head_revision()
    assert ENDING_SOON_COLUMNS <= _column_names(db_path, "settings")

    # THEN: Both columns are NOT NULL with the contract defaults
    conn = sqlite3.connect(db_path)
    try:
        info = {
            row[1]: row for row in conn.execute("PRAGMA table_info(settings)").fetchall()
        }
        for column in ENDING_SOON_COLUMNS:
            assert info[column][3] == 1, f"{column} must be NOT NULL"
        conn.execute(
            "INSERT INTO settings (id, user_agent, safety_check_enabled, auto_hide_unsafe, "
            "autojoin_enabled, autojoin_start_at, autojoin_stop_at, autojoin_min_price, "
            "autojoin_min_score, autojoin_min_reviews, scan_interval_minutes, "
            "automation_enabled, max_scan_pages, entry_delay_min, entry_delay_max, "
            "created_at, updated_at) VALUES (1, 'ua', 1, 1, 0, 350, 200, 10, 7, 1000, "
            "30, 0, 3, 8, 12, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
        )
        row = conn.execute(
            "SELECT ending_soon_priority_enabled, ending_soon_threshold_minutes "
            "FROM settings WHERE id = 1"
        ).fetchone()
    finally:
        conn.close()
    assert row == (0, 60)
