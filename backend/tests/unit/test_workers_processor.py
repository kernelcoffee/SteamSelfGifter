"""Unit tests for giveaway processor worker."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_process_giveaways_success():
    """Test successful giveaway processing."""
    from workers.processor import process_giveaways

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"
    mock_settings.user_agent = "Test Agent"
    mock_settings.autojoin_enabled = True
    mock_settings.autojoin_min_price = 50
    mock_settings.autojoin_min_score = 7
    mock_settings.autojoin_min_reviews = 100
    mock_settings.autojoin_max_game_age = None
    mock_settings.max_entries_per_cycle = 5
    mock_settings.entry_delay_min = 0.01
    mock_settings.entry_delay_max = 0.02

    mock_giveaway = MagicMock()
    mock_giveaway.code = "TEST123"
    mock_giveaway.game = MagicMock()
    mock_giveaway.game.name = "Test Game"

    mock_entry = MagicMock()
    mock_entry.points_spent = 50

    with patch("workers.processor.AsyncSessionLocal") as mock_session_local, \
         patch("workers.processor.SettingsService") as mock_settings_service_cls, \
         patch("workers.processor.SteamGiftsClient") as mock_sg_client_cls, \
         patch("workers.processor.SteamClient") as mock_steam_client_cls, \
         patch("workers.processor.GiveawayService") as mock_giveaway_service_cls, \
         patch("workers.processor.GameService"), \
         patch("workers.processor.NotificationService") as mock_notification_service_cls, \
         patch("workers.processor.event_manager") as mock_event_manager, \
         patch("workers.processor.asyncio.sleep", new_callable=AsyncMock):

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
        mock_giveaway_service.get_eligible_giveaways.return_value = [mock_giveaway]
        mock_giveaway_service.enter_giveaway.return_value = mock_entry
        mock_giveaway_service_cls.return_value = mock_giveaway_service

        mock_notification_service = AsyncMock()
        mock_notification_service_cls.return_value = mock_notification_service

        mock_event_manager.broadcast_event = AsyncMock()

        results = await process_giveaways()

        assert results["eligible"] == 1
        assert results["entered"] == 1
        assert results["failed"] == 0
        assert results["points_spent"] == 50
        assert results["skipped"] is False


@pytest.mark.asyncio
async def test_process_giveaways_not_authenticated():
    """Test processing skipped when not authenticated."""
    from workers.processor import process_giveaways

    mock_settings = MagicMock()
    mock_settings.phpsessid = None

    with patch("workers.processor.AsyncSessionLocal") as mock_session_local, \
         patch("workers.processor.SettingsService") as mock_settings_service_cls:

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_session_local.return_value = mock_session

        mock_settings_service = AsyncMock()
        mock_settings_service.get_settings.return_value = mock_settings
        mock_settings_service_cls.return_value = mock_settings_service

        results = await process_giveaways()

        assert results["skipped"] is True
        assert results["reason"] == "not_authenticated"


@pytest.mark.asyncio
async def test_process_giveaways_autojoin_disabled():
    """Test processing skipped when autojoin disabled."""
    from workers.processor import process_giveaways

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"
    mock_settings.autojoin_enabled = False

    with patch("workers.processor.AsyncSessionLocal") as mock_session_local, \
         patch("workers.processor.SettingsService") as mock_settings_service_cls:

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_session_local.return_value = mock_session

        mock_settings_service = AsyncMock()
        mock_settings_service.get_settings.return_value = mock_settings
        mock_settings_service_cls.return_value = mock_settings_service

        results = await process_giveaways()

        assert results["skipped"] is True
        assert results["reason"] == "autojoin_disabled"


@pytest.mark.asyncio
async def test_process_giveaways_no_eligible():
    """Test processing with no eligible giveaways."""
    from workers.processor import process_giveaways

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"
    mock_settings.user_agent = "Test Agent"
    mock_settings.autojoin_enabled = True
    mock_settings.autojoin_min_price = 50
    mock_settings.autojoin_min_score = 7
    mock_settings.autojoin_min_reviews = 100
    mock_settings.autojoin_max_game_age = None
    mock_settings.max_entries_per_cycle = 5

    with patch("workers.processor.AsyncSessionLocal") as mock_session_local, \
         patch("workers.processor.SettingsService") as mock_settings_service_cls, \
         patch("workers.processor.SteamGiftsClient") as mock_sg_client_cls, \
         patch("workers.processor.SteamClient") as mock_steam_client_cls, \
         patch("workers.processor.GiveawayService") as mock_giveaway_service_cls, \
         patch("workers.processor.GameService"), \
         patch("workers.processor.NotificationService") as mock_notification_service_cls:

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
        mock_giveaway_service.get_eligible_giveaways.return_value = []
        mock_giveaway_service_cls.return_value = mock_giveaway_service

        mock_notification_service = AsyncMock()
        mock_notification_service_cls.return_value = mock_notification_service

        results = await process_giveaways()

        assert results["eligible"] == 0
        assert results["entered"] == 0
        assert results["skipped"] is False


@pytest.mark.asyncio
async def test_process_giveaways_entry_failure():
    """Test processing handles entry failures."""
    from workers.processor import process_giveaways

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"
    mock_settings.user_agent = "Test Agent"
    mock_settings.autojoin_enabled = True
    mock_settings.autojoin_min_price = 50
    mock_settings.autojoin_min_score = 7
    mock_settings.autojoin_min_reviews = 100
    mock_settings.autojoin_max_game_age = None
    mock_settings.max_entries_per_cycle = 5
    mock_settings.entry_delay_min = 0.01
    mock_settings.entry_delay_max = 0.02

    mock_giveaway = MagicMock()
    mock_giveaway.code = "TEST123"
    mock_giveaway.game = MagicMock()
    mock_giveaway.game.name = "Test Game"

    with patch("workers.processor.AsyncSessionLocal") as mock_session_local, \
         patch("workers.processor.SettingsService") as mock_settings_service_cls, \
         patch("workers.processor.SteamGiftsClient") as mock_sg_client_cls, \
         patch("workers.processor.SteamClient") as mock_steam_client_cls, \
         patch("workers.processor.GiveawayService") as mock_giveaway_service_cls, \
         patch("workers.processor.GameService"), \
         patch("workers.processor.NotificationService") as mock_notification_service_cls, \
         patch("workers.processor.event_manager") as mock_event_manager, \
         patch("workers.processor.asyncio.sleep", new_callable=AsyncMock):

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
        mock_giveaway_service.get_eligible_giveaways.return_value = [mock_giveaway]
        mock_giveaway_service.enter_giveaway.return_value = None  # Entry failed
        mock_giveaway_service_cls.return_value = mock_giveaway_service

        mock_notification_service = AsyncMock()
        mock_notification_service_cls.return_value = mock_notification_service

        mock_event_manager.broadcast_event = AsyncMock()

        results = await process_giveaways()

        assert results["eligible"] == 1
        assert results["entered"] == 0
        assert results["failed"] == 1


@pytest.mark.asyncio
async def test_process_giveaways_entry_error():
    """Test processing handles entry errors."""
    from workers.processor import process_giveaways

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"
    mock_settings.user_agent = "Test Agent"
    mock_settings.autojoin_enabled = True
    mock_settings.autojoin_min_price = 50
    mock_settings.autojoin_min_score = 7
    mock_settings.autojoin_min_reviews = 100
    mock_settings.autojoin_max_game_age = None
    mock_settings.max_entries_per_cycle = 5
    mock_settings.entry_delay_min = 0.01
    mock_settings.entry_delay_max = 0.02

    mock_giveaway = MagicMock()
    mock_giveaway.code = "TEST123"
    mock_giveaway.game = MagicMock()
    mock_giveaway.game.name = "Test Game"

    with patch("workers.processor.AsyncSessionLocal") as mock_session_local, \
         patch("workers.processor.SettingsService") as mock_settings_service_cls, \
         patch("workers.processor.SteamGiftsClient") as mock_sg_client_cls, \
         patch("workers.processor.SteamClient") as mock_steam_client_cls, \
         patch("workers.processor.GiveawayService") as mock_giveaway_service_cls, \
         patch("workers.processor.GameService"), \
         patch("workers.processor.NotificationService") as mock_notification_service_cls, \
         patch("workers.processor.event_manager") as mock_event_manager, \
         patch("workers.processor.asyncio.sleep", new_callable=AsyncMock):

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
        mock_giveaway_service.get_eligible_giveaways.return_value = [mock_giveaway]
        mock_giveaway_service.enter_giveaway.side_effect = Exception("Entry error")
        mock_giveaway_service_cls.return_value = mock_giveaway_service

        mock_notification_service = AsyncMock()
        mock_notification_service_cls.return_value = mock_notification_service

        mock_event_manager.broadcast_event = AsyncMock()

        results = await process_giveaways()

        assert results["eligible"] == 1
        assert results["entered"] == 0
        assert results["failed"] == 1


@pytest.mark.asyncio
async def test_enter_single_giveaway_success():
    """Test single giveaway entry success."""
    from workers.processor import enter_single_giveaway

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"
    mock_settings.user_agent = "Test Agent"

    mock_entry = MagicMock()
    mock_entry.points_spent = 50

    with patch("workers.processor.AsyncSessionLocal") as mock_session_local, \
         patch("workers.processor.SettingsService") as mock_settings_service_cls, \
         patch("workers.processor.SteamGiftsClient") as mock_sg_client_cls, \
         patch("workers.processor.SteamClient") as mock_steam_client_cls, \
         patch("workers.processor.GiveawayService") as mock_giveaway_service_cls, \
         patch("workers.processor.GameService"):

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
        mock_giveaway_service.enter_giveaway.return_value = mock_entry
        mock_giveaway_service_cls.return_value = mock_giveaway_service

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

    with patch("workers.processor.AsyncSessionLocal") as mock_session_local, \
         patch("workers.processor.SettingsService") as mock_settings_service_cls:

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_session_local.return_value = mock_session

        mock_settings_service = AsyncMock()
        mock_settings_service.get_settings.return_value = mock_settings
        mock_settings_service_cls.return_value = mock_settings_service

        result = await enter_single_giveaway("TEST123")

        assert result["success"] is False
        assert result["error"] == "Not authenticated"


@pytest.mark.asyncio
async def test_enter_single_giveaway_failure():
    """Test single entry failure."""
    from workers.processor import enter_single_giveaway

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"
    mock_settings.user_agent = "Test Agent"

    with patch("workers.processor.AsyncSessionLocal") as mock_session_local, \
         patch("workers.processor.SettingsService") as mock_settings_service_cls, \
         patch("workers.processor.SteamGiftsClient") as mock_sg_client_cls, \
         patch("workers.processor.SteamClient") as mock_steam_client_cls, \
         patch("workers.processor.GiveawayService") as mock_giveaway_service_cls, \
         patch("workers.processor.GameService"):

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
        mock_giveaway_service.enter_giveaway.return_value = None
        mock_giveaway_service_cls.return_value = mock_giveaway_service

        result = await enter_single_giveaway("TEST123")

        assert result["success"] is False
        assert result["error"] == "Entry failed"


@pytest.mark.asyncio
async def test_enter_single_giveaway_error():
    """Test single entry with error."""
    from workers.processor import enter_single_giveaway

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"
    mock_settings.user_agent = "Test Agent"

    with patch("workers.processor.AsyncSessionLocal") as mock_session_local, \
         patch("workers.processor.SettingsService") as mock_settings_service_cls, \
         patch("workers.processor.SteamGiftsClient") as mock_sg_client_cls, \
         patch("workers.processor.SteamClient") as mock_steam_client_cls, \
         patch("workers.processor.GiveawayService") as mock_giveaway_service_cls, \
         patch("workers.processor.GameService"):

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
        mock_giveaway_service.enter_giveaway.side_effect = Exception("API error")
        mock_giveaway_service_cls.return_value = mock_giveaway_service

        result = await enter_single_giveaway("TEST123")

        assert result["success"] is False
        assert result["error"] == "API error"
