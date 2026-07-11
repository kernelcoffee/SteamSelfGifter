"""Unit tests for giveaway processor worker."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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
    mock_settings.max_entries_per_cycle = 5
    mock_settings.entry_delay_min = 0.01
    mock_settings.entry_delay_max = 0.02
    mock_settings.safety_check_enabled = False
    for key, value in overrides.items():
        setattr(mock_settings, key, value)
    return mock_settings


@pytest.mark.asyncio
async def test_process_giveaways_success():
    """Test successful giveaway processing."""
    from workers.processor import process_giveaways

    mock_settings = _autojoin_settings()

    mock_giveaway = MagicMock()
    mock_giveaway.code = "TEST123"
    mock_giveaway.game_name = "Test Game"

    mock_entry = MagicMock()
    mock_entry.points_spent = 50

    mock_giveaway_service = AsyncMock()
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

    mock_giveaway = MagicMock()
    mock_giveaway.code = "TEST123"
    mock_giveaway.game_name = "Test Game"

    mock_giveaway_service = AsyncMock()
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

    mock_giveaway = MagicMock()
    mock_giveaway.code = "TEST123"
    mock_giveaway.game_name = "Test Game"

    mock_giveaway_service = AsyncMock()
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

    mock_giveaway = MagicMock()
    mock_giveaway.code = "TEST123"
    mock_giveaway.game_name = "Test Game"

    mock_entry = MagicMock()
    mock_entry.points_spent = 50

    mock_giveaway_service = AsyncMock()
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
