"""Unit tests for win detection and tracking functionality."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock


class TestSteamGiftsClientGetWonGiveaways:
    """Tests for SteamGiftsClient.get_won_giveaways method."""

    @pytest.fixture
    def sample_won_html(self):
        """Sample HTML from /giveaways/won page (actual structure from SteamGifts)."""
        return """
        <div class="table__row-inner-wrap">
            <div>
                <a class="table_image_thumbnail" style="background-image:url(https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/620/capsule_184x69.jpg);" href="/giveaway/AbCd1/portal-2"></a>
            </div>
            <div class="table__column--width-fill">
                <p><a class="table__column__heading" href="/giveaway/AbCd1/portal-2">Portal 2</a></p>
                <p>Ended <span data-timestamp="1704067200">1 year</span> ago</p>
            </div>
            <div class="table__column--width-medium text-center">
                <div class="table__column__key"><i data-clipboard-text="AAAAA-BBBBB-CCCCC" class="icon_to_clipboard fa fa-fw fa-copy"></i><span>AAAAA-BBBBB-CCCCC</span></div>
            </div>
            <div class="table__column--width-small text-center table__column--gift-feedback">
                <div><i class="icon-green fa fa-check-circle"></i> Received</div>
            </div>
        </div>
        <div class="table__row-inner-wrap">
            <div>
                <a class="table_image_thumbnail" style="background-image:url(https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/220/capsule_184x69.jpg);" href="/giveaway/XyZ99/half-life-2"></a>
            </div>
            <div class="table__column--width-fill">
                <p><a class="table__column__heading" href="/giveaway/XyZ99/half-life-2">Half-Life 2</a></p>
                <p>Ended <span data-timestamp="1704153600">1 year</span> ago</p>
            </div>
            <div class="table__column--width-medium text-center">
                <div class="table__column__key"><i data-clipboard-text="DDDDD-EEEEE-FFFFF" class="icon_to_clipboard fa fa-fw fa-copy"></i><span>DDDDD-EEEEE-FFFFF</span></div>
            </div>
            <div class="table__column--width-small text-center table__column--gift-feedback">
                <div><i class="fa fa-circle-o"></i> Not Received</div>
            </div>
        </div>
        """

    @pytest.mark.asyncio
    async def test_parse_won_giveaways(self, sample_won_html):
        """Test parsing won giveaways from HTML."""
        from utils.steamgifts_client import SteamGiftsClient
        from bs4 import BeautifulSoup

        client = SteamGiftsClient(phpsessid="test", user_agent="test")

        soup = BeautifulSoup(sample_won_html, "html.parser")
        rows = soup.find_all("div", class_="table__row-inner-wrap")

        results = []
        for row in rows:
            result = client._parse_won_giveaway_row(row)
            if result:
                results.append(result)

        assert len(results) == 2

        # Check first win
        assert results[0]["code"] == "AbCd1"
        assert results[0]["game_name"] == "Portal 2"
        assert results[0]["game_id"] == 620
        assert results[0]["received"] is True
        assert results[0]["steam_key"] == "AAAAA-BBBBB-CCCCC"

        # Check second win
        assert results[1]["code"] == "XyZ99"
        assert results[1]["game_name"] == "Half-Life 2"
        assert results[1]["game_id"] == 220
        assert results[1]["received"] is False
        assert results[1]["steam_key"] == "DDDDD-EEEEE-FFFFF"

    @pytest.mark.asyncio
    async def test_get_won_giveaways_fetches_page(self, sample_won_html):
        """Test that get_won_giveaways fetches the correct page."""
        from utils.steamgifts_client import SteamGiftsClient

        client = SteamGiftsClient(phpsessid="test", user_agent="test")

        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = sample_won_html

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._client = mock_http_client

        wins = await client.get_won_giveaways(page=1)

        # Verify correct URL was called
        mock_http_client.get.assert_called_once()
        call_args = mock_http_client.get.call_args
        assert "/giveaways/won" in str(call_args)

        assert len(wins) == 2

    @pytest.mark.asyncio
    async def test_parse_won_giveaway_missing_link(self):
        """Test parsing fails gracefully when link is missing."""
        from utils.steamgifts_client import SteamGiftsClient
        from bs4 import BeautifulSoup

        html = '<div class="table__row-inner-wrap"><div>No link here</div></div>'
        soup = BeautifulSoup(html, "html.parser")
        row = soup.find("div", class_="table__row-inner-wrap")

        client = SteamGiftsClient(phpsessid="test", user_agent="test")
        result = client._parse_won_giveaway_row(row)

        assert result is None


class TestGiveawayRepositoryWins:
    """Tests for GiveawayRepository win-related methods."""

    @pytest.mark.asyncio
    async def test_get_won_returns_won_giveaways(self):
        """Test get_won returns only won giveaways."""
        from unittest.mock import MagicMock

        # Create mock giveaways
        won_giveaway = MagicMock()
        won_giveaway.is_won = True
        won_giveaway.won_at = datetime(2025, 1, 1)

        # Mock the repository
        from repositories.giveaway import GiveawayRepository

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [won_giveaway]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = GiveawayRepository(mock_session)
        wins = await repo.get_won(limit=10)

        assert len(wins) == 1
        assert wins[0].is_won is True

    @pytest.mark.asyncio
    async def test_count_won_returns_correct_count(self):
        """Test count_won returns correct count."""
        from repositories.giveaway import GiveawayRepository

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = GiveawayRepository(mock_session)
        count = await repo.count_won()

        assert count == 5


class TestGiveawayRepositoryNextExpiring:
    """Tests for GiveawayRepository.get_next_expiring_entered method."""

    @pytest.mark.asyncio
    async def test_get_next_expiring_entered_returns_soonest(self):
        """Test get_next_expiring_entered returns the soonest expiring giveaway."""
        from datetime import timedelta
        from repositories.giveaway import GiveawayRepository

        # Create mock giveaways with different end times
        now = datetime.utcnow()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_giveaway = MagicMock()
        mock_giveaway.end_time = now + timedelta(hours=2)
        mock_result.scalar_one_or_none.return_value = mock_giveaway
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = GiveawayRepository(mock_session)
        result = await repo.get_next_expiring_entered()

        assert result == mock_giveaway

    @pytest.mark.asyncio
    async def test_get_next_expiring_entered_none_when_empty(self):
        """Test get_next_expiring_entered returns None when no entered giveaways."""
        from repositories.giveaway import GiveawayRepository

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = GiveawayRepository(mock_session)
        result = await repo.get_next_expiring_entered()

        assert result is None


class TestGiveawayServiceSyncWins:
    """Tests for GiveawayService.sync_wins method."""

    @pytest.mark.asyncio
    async def test_sync_wins_marks_existing_giveaway_as_won(self):
        """Test that sync_wins marks existing giveaways as won."""
        from services.giveaway_service import GiveawayService

        # Create mock dependencies
        mock_session = AsyncMock()
        mock_sg_client = AsyncMock()
        mock_game_service = AsyncMock()

        # Mock won data from SteamGifts
        mock_sg_client.get_won_giveaways = AsyncMock(return_value=[
            {
                "code": "AbCd1",
                "game_name": "Portal 2",
                "game_id": 620,
                "won_at": datetime(2025, 1, 1),
                "received": True,
            }
        ])

        # Create mock giveaway that exists but isn't won yet
        mock_giveaway = MagicMock()
        mock_giveaway.is_won = False
        mock_giveaway.code = "AbCd1"

        # Create service with mocked repo
        service = GiveawayService(mock_session, mock_sg_client, mock_game_service)
        service.giveaway_repo = AsyncMock()
        service.giveaway_repo.get_by_code = AsyncMock(return_value=mock_giveaway)

        new_wins = await service.sync_wins(pages=1)

        assert new_wins == 1
        assert mock_giveaway.is_won is True
        assert mock_giveaway.won_at is not None

    @pytest.mark.asyncio
    async def test_sync_wins_creates_new_giveaway_for_unknown_win(self):
        """Test that sync_wins creates giveaway for wins not in database."""
        from services.giveaway_service import GiveawayService

        mock_session = AsyncMock()
        mock_sg_client = AsyncMock()
        mock_game_service = AsyncMock()

        mock_sg_client.get_won_giveaways = AsyncMock(return_value=[
            {
                "code": "NewWin",
                "game_name": "New Game",
                "game_id": 999,
                "won_at": datetime(2025, 1, 1),
                "received": False,
            }
        ])

        service = GiveawayService(mock_session, mock_sg_client, mock_game_service)
        service.giveaway_repo = AsyncMock()
        service.giveaway_repo.get_by_code = AsyncMock(return_value=None)
        service.giveaway_repo.create = AsyncMock()

        new_wins = await service.sync_wins(pages=1)

        assert new_wins == 1
        service.giveaway_repo.create.assert_called_once()

        # Verify the created giveaway has correct fields
        call_kwargs = service.giveaway_repo.create.call_args.kwargs
        assert call_kwargs["code"] == "NewWin"
        assert call_kwargs["is_won"] is True
        assert call_kwargs["is_entered"] is True

    @pytest.mark.asyncio
    async def test_sync_wins_skips_already_won_giveaways(self):
        """Test that sync_wins doesn't re-mark already won giveaways."""
        from services.giveaway_service import GiveawayService

        mock_session = AsyncMock()
        mock_sg_client = AsyncMock()
        mock_game_service = AsyncMock()

        mock_sg_client.get_won_giveaways = AsyncMock(return_value=[
            {
                "code": "AlreadyWon",
                "game_name": "Already Won Game",
                "game_id": 111,
                "won_at": datetime(2025, 1, 1),
                "received": True,
            }
        ])

        # Giveaway already marked as won
        mock_giveaway = MagicMock()
        mock_giveaway.is_won = True
        mock_giveaway.code = "AlreadyWon"

        service = GiveawayService(mock_session, mock_sg_client, mock_game_service)
        service.giveaway_repo = AsyncMock()
        service.giveaway_repo.get_by_code = AsyncMock(return_value=mock_giveaway)

        new_wins = await service.sync_wins(pages=1)

        assert new_wins == 0  # No new wins since already marked
