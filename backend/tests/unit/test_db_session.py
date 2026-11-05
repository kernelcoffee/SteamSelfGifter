"""Unit tests for database session management.

This module contains tests for the database session management functionality, including:
- Async session generator yielding AsyncSession instances
- Context manager behavior for proper cleanup
- Session independence across multiple calls
- init_db migration behavior for fresh and legacy (untracked) databases
"""

import asyncio
import json
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

    # AND: Re-upgrading works (downgrade left no residue); the genres revision
    # is the last one that still has these columns (b7e2d9c4a1f6 drops them)
    await asyncio.to_thread(command.upgrade, cfg, "f5b2d8c3a7e1")
    assert _db_revision(db_path) == "f5b2d8c3a7e1"
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


GENRES_REVISION = "f5b2d8c3a7e1"
GAME_GENRE_COLUMNS = {"genres", "categories"}


def _insert_legacy_settings_and_game(db_path):
    """Insert one settings row and one games row without the genre columns."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO settings (id, user_agent, safety_check_enabled, auto_hide_unsafe, "
            "autojoin_enabled, autojoin_start_at, autojoin_stop_at, autojoin_min_price, "
            "autojoin_min_score, autojoin_min_reviews, scan_interval_minutes, "
            "automation_enabled, max_scan_pages, entry_delay_min, entry_delay_max, "
            "created_at, updated_at) VALUES (1, 'ua', 1, 1, 0, 350, 200, 10, 7, 1000, "
            "30, 0, 3, 8, 12, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
        )
        conn.execute(
            "INSERT INTO games (id, name, type, is_bundle, review_score, total_positive, "
            "total_negative, total_reviews, last_refreshed_at, "
            "created_at, updated_at) VALUES (620, 'Portal 2', 'game', 0, 9, 10, 1, 11, "
            "'2026-01-01 00:00:00', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_genres_migration_upgrade_backfills_and_downgrade_drops(tmp_path, monkeypatch):
    """The genres revision revises e3a9c7b5d1f4 and lies on the single head's
    lineage; upgrading a database with existing rows leaves games.genres and
    games.categories NULL ("not fetched yet", so a refresh backfills them)
    and sets settings.excluded_genres to '[]'; downgrade drops all three and
    keeps the rows."""
    from alembic.script import ScriptDirectory

    from alembic import command

    # GIVEN: A database at the ending-soon revision with a settings and a games row
    db_path = tmp_path / "genres.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    await asyncio.to_thread(command.upgrade, cfg, ENDING_SOON_REVISION)
    assert GAME_GENRE_COLUMNS.isdisjoint(_column_names(db_path, "games"))
    assert "excluded_genres" not in _column_names(db_path, "settings")
    _insert_legacy_settings_and_game(db_path)

    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1
    lineage = {rev.revision for rev in script.iterate_revisions(heads[0], "base")}
    assert GENRES_REVISION in lineage
    assert script.get_revision(GENRES_REVISION).down_revision == ENDING_SOON_REVISION

    # WHEN: Upgrading to the genres revision
    await asyncio.to_thread(command.upgrade, cfg, GENRES_REVISION)

    # THEN: The columns exist; the game row is unfetched, settings got '[]'
    assert _db_revision(db_path) == GENRES_REVISION
    assert GAME_GENRE_COLUMNS <= _column_names(db_path, "games")
    assert "excluded_genres" in _column_names(db_path, "settings")
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute(
            "SELECT genres, categories FROM games WHERE id = 620"
        ).fetchone() == (None, None)
        assert conn.execute(
            "SELECT excluded_genres FROM settings WHERE id = 1"
        ).fetchone() == ("[]",)
    finally:
        conn.close()

    # WHEN: Downgrading back to the ending-soon revision
    await asyncio.to_thread(command.downgrade, cfg, ENDING_SOON_REVISION)

    # THEN: All three columns are gone and both rows survive
    assert _db_revision(db_path) == ENDING_SOON_REVISION
    assert GAME_GENRE_COLUMNS.isdisjoint(_column_names(db_path, "games"))
    assert "excluded_genres" not in _column_names(db_path, "settings")
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 1
        assert conn.execute("SELECT name FROM games WHERE id = 620").fetchone() == ("Portal 2",)
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_genres_migration_round_trip_on_empty_database(tmp_path, monkeypatch):
    """On an empty database the genres revision upgrades, downgrades and
    re-upgrades cleanly; excluded_genres is NOT NULL with default '[]' and the
    game columns are nullable."""
    from alembic import command

    # GIVEN: A brand-new empty database
    db_path = tmp_path / "genres_empty.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    # WHEN: Upgrading to head, back to the ending-soon revision, and to head again
    await asyncio.to_thread(command.upgrade, cfg, "head")
    assert GAME_GENRE_COLUMNS <= _column_names(db_path, "games")
    await asyncio.to_thread(command.downgrade, cfg, ENDING_SOON_REVISION)
    assert _db_revision(db_path) == ENDING_SOON_REVISION
    assert GAME_GENRE_COLUMNS.isdisjoint(_column_names(db_path, "games"))
    assert "excluded_genres" not in _column_names(db_path, "settings")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    assert _db_revision(db_path) == _head_revision()

    # THEN: Nullability and defaults match the model
    conn = sqlite3.connect(db_path)
    try:
        games_info = {r[1]: r for r in conn.execute("PRAGMA table_info(games)").fetchall()}
        settings_info = {r[1]: r for r in conn.execute("PRAGMA table_info(settings)").fetchall()}
    finally:
        conn.close()
    for column in GAME_GENRE_COLUMNS:
        assert games_info[column][3] == 0, f"games.{column} must be nullable"
    assert settings_info["excluded_genres"][3] == 1
    assert settings_info["excluded_genres"][4] == "'[]'"

    # AND: A row inserted without the new columns gets the defaults
    _insert_legacy_settings_and_game(db_path)
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT excluded_genres FROM settings").fetchone() == ("[]",)
        assert conn.execute("SELECT genres FROM games").fetchone() == (None,)
    finally:
        conn.close()


AUTOJOIN_REVISION = "b7e2d9c4a1f6"
FLAG_COLUMNS = (
    "wishlist_priority_enabled", "dlc_priority_enabled",
    "ending_soon_priority_enabled", "ending_soon_threshold_minutes",
)


def _table_info(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return [row for row in conn.execute(f"PRAGMA table_info({table})")]
    finally:
        conn.close()


def _seed_pre_autojoin_rows(db_path, wishlist, dlc, ending_soon):
    """A settings row with the old flags, threshold 90, a NULL cap and 0
    thresholds, plus three giveaways with old reason codes."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO settings (id, user_agent, safety_check_enabled, auto_hide_unsafe, "
            "autojoin_enabled, autojoin_start_at, autojoin_stop_at, autojoin_min_price, "
            "autojoin_min_score, autojoin_min_reviews, scan_interval_minutes, max_entries_per_cycle, "
            "automation_enabled, max_scan_pages, entry_delay_min, entry_delay_max, log_retention_days, "
            "wishlist_priority_enabled, dlc_priority_enabled, ending_soon_priority_enabled, "
            "ending_soon_threshold_minutes, excluded_genres, created_at, updated_at) "
            "VALUES (1, 'ua', 1, 1, 1, 350, 200, 10, 0, 0, 30, NULL, 0, 3, 8, 12, 30, ?, ?, ?, 90, "
            "'[\"Sports\"]', '2026-01-01 00:00:00', '2026-01-01 00:00:00')",
            (int(wishlist), int(dlc), int(ending_soon)),
        )
        for code, reason in (("MAXP1", "price_above_max"), ("ELIG1", "eligible"), ("NULL1", None)):
            conn.execute(
                "INSERT INTO giveaways (code, url, game_name, price, copies, entries, is_hidden, is_entered, "
                "is_wishlist, is_dlc, is_won, eligibility_reason, eligibility_checked_at, discovered_at, "
                "created_at, updated_at) VALUES (?, 'u', 'g', 10, 1, 0, 0, 0, 0, 0, 0, ?, ?, "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00', '2026-01-01 00:00:00')",
                (code, reason, "2026-01-02 00:00:00" if reason else None),
            )
        conn.commit()
    finally:
        conn.close()


def _query(db_path, sql):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("wishlist", [False, True])
@pytest.mark.parametrize("dlc", [False, True])
@pytest.mark.parametrize("ending_soon", [False, True])
async def test_autojoin_priorities_migration_round_trip(tmp_path, monkeypatch, wishlist, dlc, ending_soon):
    """b7e2d9c4a1f6 maps the old flags to the priority list in the order
    wishlist, dlc, ending_soon (the threshold moves into the item), adds
    included_genres after excluded_genres, makes the cap NOT NULL (NULL -> 10)
    and the score/reviews thresholds nullable (0 kept), adds
    eligibility_detail and nulls the dropped price_above_max code; downgrade
    restores the flags, and upgrading again rebuilds the same list."""
    from alembic import command

    db_path = tmp_path / "autojoin.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    await asyncio.to_thread(command.upgrade, cfg, GENRES_REVISION)
    _seed_pre_autojoin_rows(db_path, wishlist, dlc, ending_soon)

    expected = []
    if wishlist:
        expected.append({"type": "wishlist"})
    if dlc:
        expected.append({"type": "dlc"})
    if ending_soon:
        expected.append({"type": "ending_soon", "threshold_minutes": 90})

    # WHEN: upgrading to the auto-join revision
    await asyncio.to_thread(command.upgrade, cfg, AUTOJOIN_REVISION)

    # THEN: the list, the dropped columns, the cap, the nullable thresholds
    assert _db_revision(db_path) == AUTOJOIN_REVISION
    assert _follows_in_head_lineage(AUTOJOIN_REVISION, GENRES_REVISION)
    info = {row[1]: row for row in _table_info(db_path, "settings")}
    order = [row[1] for row in _table_info(db_path, "settings")]
    assert set(FLAG_COLUMNS).isdisjoint(info)
    assert order.index("included_genres") == order.index("excluded_genres") + 1
    assert order.index("autojoin_priorities") == order.index("included_genres") + 1
    assert (info["included_genres"][3], info["included_genres"][4]) == (1, "'[]'")
    assert info["autojoin_priorities"][3] == 1
    assert (info["max_entries_per_cycle"][3], info["max_entries_per_cycle"][4]) == (1, "'10'")
    assert info["autojoin_min_score"][3] == 0 and info["autojoin_min_reviews"][3] == 0
    [(priorities, included, excluded, cap, min_score, min_reviews)] = _query(
        db_path, "SELECT autojoin_priorities, included_genres, excluded_genres, max_entries_per_cycle, "
                 "autojoin_min_score, autojoin_min_reviews FROM settings",
    )
    assert json.loads(priorities) == expected
    assert (included, excluded, cap, min_score, min_reviews) == ("[]", '["Sports"]', 10, 0, 0)
    giveaways_info = {row[1]: row for row in _table_info(db_path, "giveaways")}
    assert giveaways_info["eligibility_detail"][3] == 0
    rows = dict(
        (code, (reason, checked, detail)) for code, reason, checked, detail in _query(
            db_path, "SELECT code, eligibility_reason, eligibility_checked_at, eligibility_detail FROM giveaways",
        )
    )
    assert rows["MAXP1"] == (None, None, None)
    assert rows["ELIG1"] == ("eligible", "2026-01-02 00:00:00", None)
    assert rows["NULL1"] == (None, None, None)

    # WHEN: setting an include list and NULL thresholds, then downgrading
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE settings SET included_genres = '[\"RPG\"]', autojoin_min_score = NULL, "
                 "autojoin_min_reviews = NULL")
    conn.commit()
    conn.close()
    await asyncio.to_thread(command.downgrade, cfg, GENRES_REVISION)

    # THEN: the flags come back from the list; the include list and detail are gone
    assert _db_revision(db_path) == GENRES_REVISION
    info = {row[1]: row for row in _table_info(db_path, "settings")}
    assert {"autojoin_priorities", "included_genres"}.isdisjoint(info)
    assert "eligibility_detail" not in _column_names(db_path, "giveaways")
    assert info["autojoin_min_score"][3] == 1 and info["autojoin_min_reviews"][3] == 1
    assert info["max_entries_per_cycle"][3] == 0
    [flags] = _query(
        db_path, "SELECT wishlist_priority_enabled, dlc_priority_enabled, ending_soon_priority_enabled, "
                 "ending_soon_threshold_minutes, autojoin_min_score, autojoin_min_reviews, max_entries_per_cycle "
                 "FROM settings",
    )
    assert flags == (int(wishlist), int(dlc), int(ending_soon), 90 if ending_soon else 60, 7, 1000, 10)

    # WHEN/THEN: upgrading again rebuilds the same list; the include list was lost
    await asyncio.to_thread(command.upgrade, cfg, AUTOJOIN_REVISION)
    [(priorities, included)] = _query(db_path, "SELECT autojoin_priorities, included_genres FROM settings")
    assert json.loads(priorities) == expected
    assert included == "[]"


def _follows_in_head_lineage(revision, parent):
    """Whether ``revision`` sits on the single head's lineage, directly after ``parent``.

    Head-independent: a later revision built on ``revision`` keeps it true.
    """
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config())
    heads = script.get_heads()
    if len(heads) != 1:
        return False
    lineage = {rev.revision for rev in script.iterate_revisions(heads[0], "base")}
    return revision in lineage and script.get_revision(revision).down_revision == parent


@pytest.mark.asyncio
@pytest.mark.parametrize("stored, expected", [
    ([{"type": "dlc"}, {"type": "ending_soon", "threshold_minutes": 120}], (0, 1, 1, 120)),
    ([], (0, 0, 0, 60)),
    ([{"type": "ending_soon", "threshold_minutes": 5}, {"type": "wishlist"}], (1, 0, 1, 5)),
])
async def test_autojoin_migration_downgrade_derives_flags_from_any_list(tmp_path, monkeypatch, stored, expected):
    """A list the UI built (any order, any subset) downgrades to flag = type present."""
    from alembic import command

    db_path = tmp_path / "autojoin_down.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    await asyncio.to_thread(command.upgrade, cfg, GENRES_REVISION)
    _seed_pre_autojoin_rows(db_path, True, False, False)
    await asyncio.to_thread(command.upgrade, cfg, AUTOJOIN_REVISION)
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE settings SET autojoin_priorities = ?", (json.dumps(stored),))
    conn.commit()
    conn.close()

    await asyncio.to_thread(command.downgrade, cfg, GENRES_REVISION)

    [flags] = _query(
        db_path, "SELECT wishlist_priority_enabled, dlc_priority_enabled, ending_soon_priority_enabled, "
                 "ending_soon_threshold_minutes FROM settings",
    )
    assert flags == expected


@pytest.mark.asyncio
async def test_autojoin_migration_on_an_empty_database_matches_the_model_defaults(tmp_path, monkeypatch):
    """With no settings row the data steps are no-ops; a row inserted after
    upgrade gets the server defaults, equal to the ORM defaults."""
    from alembic import command

    db_path = tmp_path / "autojoin_empty.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.downgrade, cfg, GENRES_REVISION)
    await asyncio.to_thread(command.upgrade, cfg, "head")

    _insert_legacy_settings_and_game(db_path)

    [row] = _query(db_path, "SELECT autojoin_priorities, included_genres, max_entries_per_cycle FROM settings")
    assert (json.loads(row[0]), row[1], row[2]) == ([{"type": "wishlist"}], "[]", 10)


@pytest.mark.asyncio
async def test_autojoin_migration_downgrade_refuses_a_non_list(tmp_path, monkeypatch):
    """A stored value that is not a list is not guessed into flags."""
    from alembic import command

    db_path = tmp_path / "autojoin_bad.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    await asyncio.to_thread(command.upgrade, cfg, GENRES_REVISION)
    _seed_pre_autojoin_rows(db_path, True, False, False)
    await asyncio.to_thread(command.upgrade, cfg, AUTOJOIN_REVISION)
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE settings SET autojoin_priorities = '{\"type\": \"wishlist\"}'")
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="not a list"):
        await asyncio.to_thread(command.downgrade, cfg, GENRES_REVISION)
