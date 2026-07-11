"""Unit tests for giveaway scanner worker."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import patch_automation_context


@pytest.mark.asyncio
async def test_scan_giveaways_success():
    """Test successful giveaway scan."""
    from workers.scanner import scan_giveaways

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"
    mock_settings.max_scan_pages = 3

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.sync_giveaways.return_value = (5, 2)

    patcher, ctx = patch_automation_context(
        "workers.scanner", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher, patch("workers.scanner.event_manager") as mock_event_manager:
        mock_event_manager.broadcast_event = AsyncMock()

        results = await scan_giveaways()

        assert results["new"] == 5
        assert results["updated"] == 2
        assert results["pages_scanned"] == 3
        assert results["skipped"] is False
        assert "scan_time" in results

        mock_giveaway_service.sync_giveaways.assert_called_once_with(pages=3)
        mock_event_manager.broadcast_event.assert_called_once()


@pytest.mark.asyncio
async def test_scan_giveaways_not_authenticated():
    """Test scan skipped when not authenticated."""
    from workers.scanner import scan_giveaways

    mock_settings = MagicMock()
    mock_settings.phpsessid = None

    patcher, ctx = patch_automation_context("workers.scanner", mock_settings)

    with patcher:
        results = await scan_giveaways()

        assert results["skipped"] is True
        assert results["reason"] == "not_authenticated"
        assert results["new"] == 0


@pytest.mark.asyncio
async def test_scan_giveaways_error():
    """Test scan handles errors."""
    from workers.scanner import scan_giveaways

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"
    mock_settings.max_scan_pages = 3

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.sync_giveaways.side_effect = Exception("API Error")

    patcher, ctx = patch_automation_context(
        "workers.scanner", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher, patch("workers.scanner.event_manager") as mock_event_manager:
        mock_event_manager.broadcast_event = AsyncMock()

        with pytest.raises(Exception, match="API Error"):
            await scan_giveaways()

        # Verify error event was emitted
        mock_event_manager.broadcast_event.assert_called_once()


@pytest.mark.asyncio
async def test_quick_scan_success():
    """Test quick scan (single page)."""
    from workers.scanner import quick_scan

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.sync_giveaways.return_value = (2, 1)

    patcher, ctx = patch_automation_context(
        "workers.scanner", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher:
        results = await quick_scan()

        assert results["new"] == 2
        assert results["updated"] == 1
        assert results["pages_scanned"] == 1
        assert results["skipped"] is False

        mock_giveaway_service.sync_giveaways.assert_called_once_with(pages=1)


@pytest.mark.asyncio
async def test_quick_scan_not_authenticated():
    """Test quick scan skipped when not authenticated."""
    from workers.scanner import quick_scan

    mock_settings = MagicMock()
    mock_settings.phpsessid = None

    patcher, ctx = patch_automation_context("workers.scanner", mock_settings)

    with patcher:
        results = await quick_scan()

        assert results["skipped"] is True
        assert results["reason"] == "not_authenticated"


@pytest.mark.asyncio
async def test_scan_uses_settings_max_pages():
    """Test scan uses max_scan_pages from settings."""
    from workers.scanner import scan_giveaways

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"
    mock_settings.max_scan_pages = 10  # Custom value

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.sync_giveaways.return_value = (0, 0)

    patcher, ctx = patch_automation_context(
        "workers.scanner", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher, patch("workers.scanner.event_manager") as mock_event_manager:
        mock_event_manager.broadcast_event = AsyncMock()

        results = await scan_giveaways()

        assert results["pages_scanned"] == 10
        mock_giveaway_service.sync_giveaways.assert_called_once_with(pages=10)


@pytest.mark.asyncio
async def test_scan_defaults_to_3_pages():
    """Test scan defaults to 3 pages if not configured."""
    from workers.scanner import scan_giveaways

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"
    mock_settings.max_scan_pages = None  # Not configured

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.sync_giveaways.return_value = (0, 0)

    patcher, ctx = patch_automation_context(
        "workers.scanner", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher, patch("workers.scanner.event_manager") as mock_event_manager:
        mock_event_manager.broadcast_event = AsyncMock()

        results = await scan_giveaways()

        assert results["pages_scanned"] == 3
        mock_giveaway_service.sync_giveaways.assert_called_once_with(pages=3)
