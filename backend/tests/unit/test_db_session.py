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
