"""Unit tests for the automation cycle worker (the scheduled/manual engine)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import patch_automation_context


def _cycle_settings(**overrides):
    """Settings mock with the fields automation_cycle reads."""
    s = MagicMock()
    s.phpsessid = "test_session"
    s.max_scan_pages = 3
    s.dlc_enabled = False
    s.autojoin_enabled = True
    s.autojoin_min_price = 50
    s.autojoin_min_score = 7
    s.autojoin_min_reviews = 100
    s.autojoin_max_game_age = None
    s.autojoin_start_at = 0
    s.autojoin_stop_at = 0
    s.wishlist_priority_enabled = True
    s.max_entries_per_cycle = 5
    s.entry_delay_min = 0.01
    s.entry_delay_max = 0.02
    s.safety_check_enabled = False
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


@pytest.mark.asyncio
async def test_automation_cycle_not_authenticated():
    """Cycle short-circuits when no PHPSESSID is configured."""
    from workers.automation import automation_cycle

    settings = MagicMock()
    settings.phpsessid = None

    patcher, ctx = patch_automation_context("workers.automation", settings)
    with patcher:
        results = await automation_cycle()

    assert results["skipped"] is True
    assert results["reason"] == "not_authenticated"


@pytest.mark.asyncio
async def test_automation_cycle_runs_all_steps_and_schedules_win_check():
    """Full cycle scans, syncs, enters, and schedules a win check on entry."""
    from workers.automation import automation_cycle

    settings = _cycle_settings()

    mock_giveaway = MagicMock()
    mock_giveaway.code = "GA1"
    mock_giveaway.price = 50
    mock_giveaway.game_name = "Test Game"
    mock_giveaway.is_wishlist = False

    mock_entry = MagicMock()
    mock_entry.points_spent = 50

    gs = AsyncMock()
    gs.get_current_points.return_value = 500
    gs.sync_giveaways.return_value = (5, 2)   # regular + wishlist both use this
    gs.sync_wins.return_value = 1
    gs.sync_entered_giveaways.return_value = 0
    gs.evaluate_and_get_eligible.return_value = [mock_giveaway]
    gs.enter_giveaway.return_value = mock_entry

    patcher, ctx = patch_automation_context(
        "workers.automation", settings, giveaway_service=gs
    )

    with patcher, \
         patch("workers.automation.event_manager") as ev, \
         patch("workers.processor.event_manager") as ev2, \
         patch("workers.processor.asyncio.sleep", new_callable=AsyncMock):
        ev.broadcast_event = AsyncMock()
        ev2.broadcast_event = AsyncMock()

        results = await automation_cycle()

    assert results["skipped"] is False
    assert results["scan"]["new"] == 5
    assert results["wins"]["new_wins"] == 1
    assert results["entries"]["entered"] == 1
    # Entering something schedules the next win check.
    ctx.scheduler_service.schedule_next_win_check.assert_awaited()
    ev.broadcast_event.assert_any_await("automation_cycle_completed", results)


@pytest.mark.asyncio
async def test_automation_cycle_skips_entries_when_autojoin_disabled():
    """With autojoin off, the cycle still scans but does not enter."""
    from workers.automation import automation_cycle

    settings = _cycle_settings(autojoin_enabled=False)

    gs = AsyncMock()
    gs.sync_giveaways.return_value = (1, 0)
    gs.sync_wins.return_value = 0
    gs.sync_entered_giveaways.return_value = 0

    patcher, ctx = patch_automation_context(
        "workers.automation", settings, giveaway_service=gs
    )

    with patcher, patch("workers.automation.event_manager") as ev:
        ev.broadcast_event = AsyncMock()

        results = await automation_cycle()

    assert results["entries"]["skipped"] is True
    assert results["entries"]["reason"] == "autojoin_disabled"
    gs.evaluate_and_get_eligible.assert_not_called()


@pytest.mark.asyncio
async def test_sync_wins_only():
    """sync_wins_only delegates to the giveaway service via the context."""
    from workers.automation import sync_wins_only

    settings = MagicMock()
    settings.phpsessid = "test_session"

    gs = AsyncMock()
    gs.sync_wins.return_value = 3

    patcher, ctx = patch_automation_context(
        "workers.automation", settings, giveaway_service=gs
    )
    with patcher:
        results = await sync_wins_only()

    assert results == {"new_wins": 3, "skipped": False}
    gs.sync_wins.assert_awaited_once_with(pages=1)


@pytest.mark.asyncio
async def test_sync_wins_only_not_authenticated():
    """sync_wins_only skips cleanly when not authenticated."""
    from workers.automation import sync_wins_only

    settings = MagicMock()
    settings.phpsessid = None

    patcher, ctx = patch_automation_context("workers.automation", settings)
    with patcher:
        results = await sync_wins_only()

    assert results["skipped"] is True
    assert results["reason"] == "not_authenticated"
