"""Unit tests for giveaway processor worker."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import patch_automation_context


def _autojoin_settings(**overrides):
    """Build a settings mock with sensible autojoin defaults."""
    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"
    mock_settings.autojoin_enabled = True
    mock_settings.autojoin_min_price = 50
    mock_settings.autojoin_min_score = 7
    mock_settings.autojoin_min_reviews = 100
    mock_settings.autojoin_max_game_age = None
    mock_settings.autojoin_start_at = 0
    mock_settings.autojoin_stop_at = 0
    mock_settings.max_entries_per_cycle = 5
    mock_settings.entry_delay_min = 0.01
    mock_settings.entry_delay_max = 0.02
    mock_settings.safety_check_enabled = False
    for key, value in overrides.items():
        setattr(mock_settings, key, value)
    return mock_settings


def _mock_giveaway(code="TEST123", price=50, game_name="Test Game", is_wishlist=False):
    """Build a giveaway mock with the fields the processor touches."""
    mock_giveaway = MagicMock()
    mock_giveaway.code = code
    mock_giveaway.price = price
    mock_giveaway.game_name = game_name
    mock_giveaway.is_wishlist = is_wishlist
    return mock_giveaway


@pytest.mark.asyncio
async def test_process_giveaways_success():
    """Test successful giveaway processing."""
    from workers.processor import process_giveaways

    mock_settings = _autojoin_settings()

    mock_giveaway = _mock_giveaway()

    mock_entry = MagicMock()
    mock_entry.points_spent = 50

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.get_current_points.return_value = 500
    mock_giveaway_service.evaluate_and_get_eligible.return_value = [mock_giveaway]
    mock_giveaway_service.enter_giveaway.return_value = mock_entry

    patcher, ctx = patch_automation_context(
        "workers.processor", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher, \
         patch("workers.processor.event_manager") as mock_event_manager, \
         patch("workers.processor.asyncio.sleep", new_callable=AsyncMock):
        mock_event_manager.broadcast_event = AsyncMock()

        results = await process_giveaways()

        assert results["eligible"] == 1
        assert results["entered"] == 1
        assert results["failed"] == 0
        assert results["points_spent"] == 50
        assert results["skipped"] is False

        # A win check is scheduled after entering anything.
        ctx.scheduler_service.schedule_next_win_check.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_giveaways_not_authenticated():
    """Test processing skipped when not authenticated."""
    from workers.processor import process_giveaways

    mock_settings = MagicMock()
    mock_settings.phpsessid = None

    patcher, ctx = patch_automation_context("workers.processor", mock_settings)

    with patcher:
        results = await process_giveaways()

        assert results["skipped"] is True
        assert results["reason"] == "not_authenticated"


@pytest.mark.asyncio
async def test_process_giveaways_autojoin_disabled():
    """Test processing skipped when autojoin disabled."""
    from workers.processor import process_giveaways

    mock_settings = _autojoin_settings(autojoin_enabled=False)

    patcher, ctx = patch_automation_context("workers.processor", mock_settings)

    with patcher:
        results = await process_giveaways()

        assert results["skipped"] is True
        assert results["reason"] == "autojoin_disabled"


@pytest.mark.asyncio
async def test_process_giveaways_no_eligible():
    """Test processing with no eligible giveaways."""
    from workers.processor import process_giveaways

    mock_settings = _autojoin_settings()

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.get_current_points.return_value = 500
    mock_giveaway_service.evaluate_and_get_eligible.return_value = []

    patcher, ctx = patch_automation_context(
        "workers.processor", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher, patch("workers.processor.event_manager") as mock_event_manager:
        mock_event_manager.broadcast_event = AsyncMock()

        results = await process_giveaways()

        assert results["eligible"] == 0
        assert results["entered"] == 0
        assert results["skipped"] is False


@pytest.mark.asyncio
async def test_process_giveaways_entry_failure():
    """Test processing handles entry failures (enter returns None)."""
    from workers.processor import process_giveaways

    mock_settings = _autojoin_settings()

    mock_giveaway = _mock_giveaway()

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.get_current_points.return_value = 500
    mock_giveaway_service.evaluate_and_get_eligible.return_value = [mock_giveaway]
    mock_giveaway_service.enter_giveaway.return_value = None  # Entry failed

    patcher, ctx = patch_automation_context(
        "workers.processor", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher, \
         patch("workers.processor.event_manager") as mock_event_manager, \
         patch("workers.processor.asyncio.sleep", new_callable=AsyncMock):
        mock_event_manager.broadcast_event = AsyncMock()

        results = await process_giveaways()

        assert results["eligible"] == 1
        assert results["entered"] == 0
        assert results["failed"] == 1


@pytest.mark.asyncio
async def test_process_giveaways_entry_error():
    """Test processing handles entry errors (enter raises)."""
    from workers.processor import process_giveaways

    mock_settings = _autojoin_settings()

    mock_giveaway = _mock_giveaway()

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.get_current_points.return_value = 500
    mock_giveaway_service.evaluate_and_get_eligible.return_value = [mock_giveaway]
    mock_giveaway_service.enter_giveaway.side_effect = Exception("Entry error")

    patcher, ctx = patch_automation_context(
        "workers.processor", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher, \
         patch("workers.processor.event_manager") as mock_event_manager, \
         patch("workers.processor.asyncio.sleep", new_callable=AsyncMock):
        mock_event_manager.broadcast_event = AsyncMock()

        results = await process_giveaways()

        assert results["eligible"] == 1
        assert results["entered"] == 0
        assert results["failed"] == 1


@pytest.mark.asyncio
async def test_process_giveaways_safety_check_enabled():
    """When safety checks are on, entries go through enter_giveaway_with_safety_check."""
    from workers.processor import process_giveaways

    mock_settings = _autojoin_settings(safety_check_enabled=True)

    mock_giveaway = _mock_giveaway()

    mock_entry = MagicMock()
    mock_entry.points_spent = 50

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.get_current_points.return_value = 500
    mock_giveaway_service.evaluate_and_get_eligible.return_value = [mock_giveaway]
    mock_giveaway_service.enter_giveaway_with_safety_check.return_value = mock_entry

    patcher, ctx = patch_automation_context(
        "workers.processor", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher, \
         patch("workers.processor.event_manager") as mock_event_manager, \
         patch("workers.processor.asyncio.sleep", new_callable=AsyncMock):
        mock_event_manager.broadcast_event = AsyncMock()

        results = await process_giveaways()

        assert results["entered"] == 1
        mock_giveaway_service.enter_giveaway_with_safety_check.assert_awaited_once_with(
            "TEST123", entry_type="auto"
        )
        mock_giveaway_service.enter_giveaway.assert_not_called()


@pytest.mark.asyncio
async def test_process_giveaways_wishlist_entry_type():
    """Wishlist giveaways are recorded with entry_type='wishlist'."""
    from workers.processor import process_giveaways

    mock_settings = _autojoin_settings()

    wishlist_ga = _mock_giveaway(code="WISH1", is_wishlist=True)

    mock_entry = MagicMock()
    mock_entry.points_spent = 50

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.get_current_points.return_value = 500
    mock_giveaway_service.evaluate_and_get_eligible.return_value = [wishlist_ga]
    mock_giveaway_service.enter_giveaway.return_value = mock_entry

    patcher, ctx = patch_automation_context(
        "workers.processor", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher, \
         patch("workers.processor.event_manager") as mock_event_manager, \
         patch("workers.processor.asyncio.sleep", new_callable=AsyncMock):
        mock_event_manager.broadcast_event = AsyncMock()

        results = await process_giveaways()

        assert results["entered"] == 1
        mock_giveaway_service.enter_giveaway.assert_awaited_once_with(
            "WISH1", entry_type="wishlist"
        )


@pytest.mark.asyncio
async def test_process_giveaways_skipped_below_start_threshold():
    """No entries are attempted while the balance is below autojoin_start_at."""
    from workers.processor import process_giveaways

    mock_settings = _autojoin_settings(autojoin_start_at=350, autojoin_stop_at=200)

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.get_current_points.return_value = 300  # below 350

    patcher, ctx = patch_automation_context(
        "workers.processor", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher, patch("workers.processor.event_manager") as mock_event_manager:
        mock_event_manager.broadcast_event = AsyncMock()

        results = await process_giveaways()

        assert results["skipped"] is True
        assert results["reason"] == "points_below_start_threshold"
        assert results["points_available"] == 300
        assert results["entered"] == 0
        mock_giveaway_service.evaluate_and_get_eligible.assert_not_called()
        mock_giveaway_service.enter_giveaway.assert_not_called()


@pytest.mark.asyncio
async def test_process_giveaways_budget_floor_skips_expensive():
    """Entries that would draw the balance below autojoin_stop_at are skipped,
    but cheaper giveaways later in the list are still entered."""
    from workers.processor import process_giveaways

    mock_settings = _autojoin_settings(autojoin_start_at=350, autojoin_stop_at=400)

    expensive = _mock_giveaway(code="BIG", price=150)
    cheap = _mock_giveaway(code="SMALL", price=50)

    mock_entry = MagicMock()
    mock_entry.points_spent = 50

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.get_current_points.return_value = 500
    mock_giveaway_service.evaluate_and_get_eligible.return_value = [expensive, cheap]
    mock_giveaway_service.enter_giveaway.return_value = mock_entry

    patcher, ctx = patch_automation_context(
        "workers.processor", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher, \
         patch("workers.processor.event_manager") as mock_event_manager, \
         patch("workers.processor.asyncio.sleep", new_callable=AsyncMock):
        mock_event_manager.broadcast_event = AsyncMock()

        results = await process_giveaways()

        # 500 - 150 = 350 < 400 -> BIG skipped; 500 - 50 = 450 >= 400 -> SMALL entered
        assert results["skipped_budget"] == 1
        assert results["entered"] == 1
        mock_giveaway_service.enter_giveaway.assert_awaited_once_with(
            "SMALL", entry_type="auto"
        )


@pytest.mark.asyncio
async def test_process_giveaways_budget_tracks_running_balance():
    """The balance decreases as entries succeed, so later entries respect it."""
    from workers.processor import process_giveaways

    mock_settings = _autojoin_settings(autojoin_start_at=350, autojoin_stop_at=400)

    first = _mock_giveaway(code="FIRST", price=60)
    second = _mock_giveaway(code="SECOND", price=50)

    mock_entry = MagicMock()
    mock_entry.points_spent = 60

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.get_current_points.return_value = 500
    mock_giveaway_service.evaluate_and_get_eligible.return_value = [first, second]
    mock_giveaway_service.enter_giveaway.return_value = mock_entry

    patcher, ctx = patch_automation_context(
        "workers.processor", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher, \
         patch("workers.processor.event_manager") as mock_event_manager, \
         patch("workers.processor.asyncio.sleep", new_callable=AsyncMock):
        mock_event_manager.broadcast_event = AsyncMock()

        results = await process_giveaways()

        # FIRST: 500 - 60 = 440 >= 400 -> entered, balance now 440.
        # SECOND: 440 - 50 = 390 < 400 -> skipped by budget.
        assert results["entered"] == 1
        assert results["skipped_budget"] == 1
        mock_giveaway_service.enter_giveaway.assert_awaited_once_with(
            "FIRST", entry_type="auto"
        )


@pytest.mark.asyncio
async def test_enter_single_giveaway_success():
    """Test single giveaway entry success."""
    from workers.processor import enter_single_giveaway

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"

    mock_entry = MagicMock()
    mock_entry.points_spent = 50

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.enter_giveaway.return_value = mock_entry

    patcher, ctx = patch_automation_context(
        "workers.processor", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher:
        result = await enter_single_giveaway("TEST123")

        assert result["success"] is True
        assert result["points_spent"] == 50
        assert result["error"] is None

        mock_giveaway_service.enter_giveaway.assert_called_once_with(
            "TEST123",
            entry_type="manual"
        )


@pytest.mark.asyncio
async def test_enter_single_giveaway_not_authenticated():
    """Test single entry when not authenticated."""
    from workers.processor import enter_single_giveaway

    mock_settings = MagicMock()
    mock_settings.phpsessid = None

    patcher, ctx = patch_automation_context("workers.processor", mock_settings)

    with patcher:
        result = await enter_single_giveaway("TEST123")

        assert result["success"] is False
        assert result["error"] == "Not authenticated"


@pytest.mark.asyncio
async def test_enter_single_giveaway_failure():
    """Test single entry failure (enter returns None)."""
    from workers.processor import enter_single_giveaway

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.enter_giveaway.return_value = None

    patcher, ctx = patch_automation_context(
        "workers.processor", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher:
        result = await enter_single_giveaway("TEST123")

        assert result["success"] is False
        assert result["error"] == "Entry failed"


@pytest.mark.asyncio
async def test_enter_single_giveaway_error():
    """Test single entry with error (enter raises)."""
    from workers.processor import enter_single_giveaway

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.enter_giveaway.side_effect = Exception("API error")

    patcher, ctx = patch_automation_context(
        "workers.processor", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher:
        result = await enter_single_giveaway("TEST123")

        assert result["success"] is False
        assert result["error"] == "API error"
