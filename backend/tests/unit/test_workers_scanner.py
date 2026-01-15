"""Unit tests for giveaway scanner worker."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_scan_giveaways_success():
    """Test successful giveaway scan."""
    from workers.scanner import scan_giveaways

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"
    mock_settings.user_agent = "Test Agent"
    mock_settings.max_scan_pages = 3

    with patch("workers.scanner.AsyncSessionLocal") as mock_session_local, \
         patch("workers.scanner.SettingsService") as mock_settings_service_cls, \
         patch("workers.scanner.SteamGiftsClient") as mock_sg_client_cls, \
         patch("workers.scanner.SteamClient") as mock_steam_client_cls, \
         patch("workers.scanner.GameService"), \
         patch("workers.scanner.GiveawayService") as mock_giveaway_service_cls, \
         patch("workers.scanner.NotificationService") as mock_notification_service_cls, \
         patch("workers.scanner.event_manager") as mock_event_manager:

        # Setup async client mocks
        mock_sg_client = AsyncMock()
        mock_sg_client_cls.return_value = mock_sg_client

        mock_steam_client = AsyncMock()
        mock_steam_client_cls.return_value = mock_steam_client

        # Setup mocks
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_session_local.return_value = mock_session

        mock_settings_service = AsyncMock()
        mock_settings_service.get_settings.return_value = mock_settings
        mock_settings_service_cls.return_value = mock_settings_service

        mock_giveaway_service = AsyncMock()
        mock_giveaway_service.sync_giveaways.return_value = (5, 2)
        mock_giveaway_service_cls.return_value = mock_giveaway_service

        mock_notification_service = AsyncMock()
        mock_notification_service_cls.return_value = mock_notification_service

        mock_event_manager.broadcast_event = AsyncMock()

        # Run scanner
        results = await scan_giveaways()

        # Verify results
        assert results["new"] == 5
        assert results["updated"] == 2
        assert results["pages_scanned"] == 3
        assert results["skipped"] is False
        assert "scan_time" in results

        # Verify sync was called
        mock_giveaway_service.sync_giveaways.assert_called_once_with(pages=3)

        # Verify event was emitted
        mock_event_manager.broadcast_event.assert_called_once()


@pytest.mark.asyncio
async def test_scan_giveaways_not_authenticated():
    """Test scan skipped when not authenticated."""
    from workers.scanner import scan_giveaways

    mock_settings = MagicMock()
    mock_settings.phpsessid = None

    with patch("workers.scanner.AsyncSessionLocal") as mock_session_local, \
         patch("workers.scanner.SettingsService") as mock_settings_service_cls:

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_session_local.return_value = mock_session

        mock_settings_service = AsyncMock()
        mock_settings_service.get_settings.return_value = mock_settings
        mock_settings_service_cls.return_value = mock_settings_service

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
    mock_settings.user_agent = "Test Agent"
    mock_settings.max_scan_pages = 3

    with patch("workers.scanner.AsyncSessionLocal") as mock_session_local, \
         patch("workers.scanner.SettingsService") as mock_settings_service_cls, \
         patch("workers.scanner.SteamGiftsClient") as mock_sg_client_cls, \
         patch("workers.scanner.SteamClient") as mock_steam_client_cls, \
         patch("workers.scanner.GameService"), \
         patch("workers.scanner.GiveawayService") as mock_giveaway_service_cls, \
         patch("workers.scanner.NotificationService") as mock_notification_service_cls, \
         patch("workers.scanner.event_manager") as mock_event_manager:

        # Setup async client mocks
        mock_sg_client = AsyncMock()
        mock_sg_client_cls.return_value = mock_sg_client

        mock_steam_client = AsyncMock()
        mock_steam_client_cls.return_value = mock_steam_client

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_session_local.return_value = mock_session

        mock_settings_service = AsyncMock()
        mock_settings_service.get_settings.return_value = mock_settings
        mock_settings_service_cls.return_value = mock_settings_service

        mock_giveaway_service = AsyncMock()
        mock_giveaway_service.sync_giveaways.side_effect = Exception("API Error")
        mock_giveaway_service_cls.return_value = mock_giveaway_service

        mock_notification_service = AsyncMock()
        mock_notification_service_cls.return_value = mock_notification_service

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
    mock_settings.user_agent = "Test Agent"

    with patch("workers.scanner.AsyncSessionLocal") as mock_session_local, \
         patch("workers.scanner.SettingsService") as mock_settings_service_cls, \
         patch("workers.scanner.SteamGiftsClient") as mock_sg_client_cls, \
         patch("workers.scanner.SteamClient") as mock_steam_client_cls, \
         patch("workers.scanner.GameService"), \
         patch("workers.scanner.GiveawayService") as mock_giveaway_service_cls:

        # Setup async client mocks
        mock_sg_client = AsyncMock()
        mock_sg_client_cls.return_value = mock_sg_client

        mock_steam_client = AsyncMock()
        mock_steam_client_cls.return_value = mock_steam_client

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_session_local.return_value = mock_session

        mock_settings_service = AsyncMock()
        mock_settings_service.get_settings.return_value = mock_settings
        mock_settings_service_cls.return_value = mock_settings_service

        mock_giveaway_service = AsyncMock()
        mock_giveaway_service.sync_giveaways.return_value = (2, 1)
        mock_giveaway_service_cls.return_value = mock_giveaway_service

        results = await quick_scan()

        assert results["new"] == 2
        assert results["updated"] == 1
        assert results["pages_scanned"] == 1
        assert results["skipped"] is False

        # Verify only 1 page was scanned
        mock_giveaway_service.sync_giveaways.assert_called_once_with(pages=1)


@pytest.mark.asyncio
async def test_quick_scan_not_authenticated():
    """Test quick scan skipped when not authenticated."""
    from workers.scanner import quick_scan

    mock_settings = MagicMock()
    mock_settings.phpsessid = None

    with patch("workers.scanner.AsyncSessionLocal") as mock_session_local, \
         patch("workers.scanner.SettingsService") as mock_settings_service_cls:

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_session_local.return_value = mock_session

        mock_settings_service = AsyncMock()
        mock_settings_service.get_settings.return_value = mock_settings
        mock_settings_service_cls.return_value = mock_settings_service

        results = await quick_scan()

        assert results["skipped"] is True
        assert results["reason"] == "not_authenticated"


@pytest.mark.asyncio
async def test_scan_uses_settings_max_pages():
    """Test scan uses max_scan_pages from settings."""
    from workers.scanner import scan_giveaways

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"
    mock_settings.user_agent = "Test Agent"
    mock_settings.max_scan_pages = 10  # Custom value

    with patch("workers.scanner.AsyncSessionLocal") as mock_session_local, \
         patch("workers.scanner.SettingsService") as mock_settings_service_cls, \
         patch("workers.scanner.SteamGiftsClient") as mock_sg_client_cls, \
         patch("workers.scanner.SteamClient") as mock_steam_client_cls, \
         patch("workers.scanner.GameService"), \
         patch("workers.scanner.GiveawayService") as mock_giveaway_service_cls, \
         patch("workers.scanner.NotificationService") as mock_notification_service_cls, \
         patch("workers.scanner.event_manager") as mock_event_manager:

        # Setup async client mocks
        mock_sg_client = AsyncMock()
        mock_sg_client_cls.return_value = mock_sg_client

        mock_steam_client = AsyncMock()
        mock_steam_client_cls.return_value = mock_steam_client

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_session_local.return_value = mock_session

        mock_settings_service = AsyncMock()
        mock_settings_service.get_settings.return_value = mock_settings
        mock_settings_service_cls.return_value = mock_settings_service

        mock_giveaway_service = AsyncMock()
        mock_giveaway_service.sync_giveaways.return_value = (0, 0)
        mock_giveaway_service_cls.return_value = mock_giveaway_service

        mock_notification_service = AsyncMock()
        mock_notification_service_cls.return_value = mock_notification_service

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
    mock_settings.user_agent = "Test Agent"
    mock_settings.max_scan_pages = None  # Not configured

    with patch("workers.scanner.AsyncSessionLocal") as mock_session_local, \
         patch("workers.scanner.SettingsService") as mock_settings_service_cls, \
         patch("workers.scanner.SteamGiftsClient") as mock_sg_client_cls, \
         patch("workers.scanner.SteamClient") as mock_steam_client_cls, \
         patch("workers.scanner.GameService"), \
         patch("workers.scanner.GiveawayService") as mock_giveaway_service_cls, \
         patch("workers.scanner.NotificationService") as mock_notification_service_cls, \
         patch("workers.scanner.event_manager") as mock_event_manager:

        # Setup async client mocks
        mock_sg_client = AsyncMock()
        mock_sg_client_cls.return_value = mock_sg_client

        mock_steam_client = AsyncMock()
        mock_steam_client_cls.return_value = mock_steam_client

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_session_local.return_value = mock_session

        mock_settings_service = AsyncMock()
        mock_settings_service.get_settings.return_value = mock_settings
        mock_settings_service_cls.return_value = mock_settings_service

        mock_giveaway_service = AsyncMock()
        mock_giveaway_service.sync_giveaways.return_value = (0, 0)
        mock_giveaway_service_cls.return_value = mock_giveaway_service

        mock_notification_service = AsyncMock()
        mock_notification_service_cls.return_value = mock_notification_service

        mock_event_manager.broadcast_event = AsyncMock()

        results = await scan_giveaways()

        assert results["pages_scanned"] == 3
        mock_giveaway_service.sync_giveaways.assert_called_once_with(pages=3)
