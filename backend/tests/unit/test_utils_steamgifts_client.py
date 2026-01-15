"""Unit tests for SteamGiftsClient."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
import httpx

from utils.steamgifts_client import (
    SteamGiftsClient,
    SteamGiftsNotFoundError,
)
from core.exceptions import (
    SteamGiftsError,
    SteamGiftsSessionExpiredError as SteamGiftsAuthError,
)


@pytest.fixture
def steamgifts_client():
    """Create SteamGiftsClient instance."""
    client = SteamGiftsClient(
        phpsessid="test_session_id",
        user_agent="TestBot/1.0",
        xsrf_token="test_xsrf_token",
        timeout_seconds=30,
    )
    return client


@pytest.mark.asyncio
async def test_steamgifts_client_init():
    """Test SteamGiftsClient initialization."""
    client = SteamGiftsClient(
        phpsessid="abc123",
        user_agent="MyBot/1.0",
        xsrf_token="token123",
    )

    assert client.phpsessid == "abc123"
    assert client.user_agent == "MyBot/1.0"
    assert client.xsrf_token == "token123"
    assert client._client is None


@pytest.mark.asyncio
async def test_steamgifts_client_start_creates_session(steamgifts_client):
    """Test start() creates httpx client with cookies and headers."""
    # Mock the _refresh_xsrf_token to avoid making actual request
    steamgifts_client._refresh_xsrf_token = AsyncMock()

    await steamgifts_client.start()

    assert steamgifts_client._client is not None
    assert isinstance(steamgifts_client._client, httpx.AsyncClient)

    await steamgifts_client.close()


@pytest.mark.asyncio
async def test_steamgifts_client_close_cleans_session(steamgifts_client):
    """Test close() cleans up session."""
    steamgifts_client._refresh_xsrf_token = AsyncMock()

    await steamgifts_client.start()
    assert steamgifts_client._client is not None

    await steamgifts_client.close()
    assert steamgifts_client._client is None


@pytest.mark.asyncio
async def test_steamgifts_client_context_manager(steamgifts_client):
    """Test SteamGiftsClient works as async context manager."""
    steamgifts_client._refresh_xsrf_token = AsyncMock()

    async with steamgifts_client as client:
        assert client._client is not None

    # Client should be closed after context
    assert steamgifts_client._client is None


@pytest.mark.asyncio
async def test_refresh_xsrf_token_success(steamgifts_client):
    """Test XSRF token extraction from homepage."""
    mock_html = """
    <html>
        <body>
            <input type="hidden" name="xsrf_token" value="extracted_token_123" />
        </body>
    </html>
    """

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_html

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    steamgifts_client._client = mock_client
    steamgifts_client.xsrf_token = None

    await steamgifts_client._refresh_xsrf_token()

    assert steamgifts_client.xsrf_token == "extracted_token_123"


@pytest.mark.asyncio
async def test_refresh_xsrf_token_fails_on_error(steamgifts_client):
    """Test XSRF token refresh raises error on HTTP error."""
    mock_response = MagicMock()
    mock_response.status_code = 500

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    steamgifts_client._client = mock_client
    steamgifts_client.xsrf_token = None

    with pytest.raises(SteamGiftsAuthError, match="Failed to fetch homepage"):
        await steamgifts_client._refresh_xsrf_token()


@pytest.mark.asyncio
async def test_refresh_xsrf_token_fails_when_not_found(steamgifts_client):
    """Test XSRF token refresh raises error when token not in HTML."""
    mock_html = """
    <html>
        <body>
            <p>No token here</p>
        </body>
    </html>
    """

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_html

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    steamgifts_client._client = mock_client
    steamgifts_client.xsrf_token = None

    with pytest.raises(SteamGiftsAuthError, match="Could not extract XSRF token"):
        await steamgifts_client._refresh_xsrf_token()


@pytest.mark.asyncio
async def test_get_user_points_success(steamgifts_client):
    """Test getting user points from homepage."""
    mock_html = """
    <html>
        <body>
            <span class="nav__points">123P</span>
        </body>
    </html>
    """

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_html

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    steamgifts_client._client = mock_client

    points = await steamgifts_client.get_user_points()

    assert points == 123


@pytest.mark.asyncio
async def test_get_user_points_not_authenticated(steamgifts_client):
    """Test get_user_points raises error when not authenticated."""
    mock_html = """
    <html>
        <body>
            <p>Not logged in</p>
        </body>
    </html>
    """

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_html

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    steamgifts_client._client = mock_client

    with pytest.raises(SteamGiftsAuthError, match="Could not find points"):
        await steamgifts_client.get_user_points()


@pytest.mark.asyncio
async def test_get_giveaways_success(steamgifts_client):
    """Test fetching giveaways list."""
    mock_html = """
    <html>
        <body>
            <div class="giveaway__row-inner-wrap">
                <a href="/giveaway/AbCd1/test-game" class="giveaway__heading__name">Test Game</a>
                <span class="giveaway__heading__thin">(50P)</span>
                <span data-timestamp="1609459200"></span>
            </div>
        </body>
    </html>
    """

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_html

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    steamgifts_client._client = mock_client

    giveaways = await steamgifts_client.get_giveaways(page=1)

    assert len(giveaways) == 1
    assert giveaways[0]["code"] == "AbCd1"
    assert giveaways[0]["game_name"] == "Test Game"
    assert giveaways[0]["price"] == 50


@pytest.mark.asyncio
async def test_get_giveaways_with_search(steamgifts_client):
    """Test fetching giveaways with search query."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body></body></html>"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    steamgifts_client._client = mock_client

    await steamgifts_client.get_giveaways(page=2, search_query="portal")

    # Verify correct params were passed
    mock_client.get.assert_called_once()
    call_args = mock_client.get.call_args
    assert call_args[1]["params"]["page"] == 2
    assert call_args[1]["params"]["q"] == "portal"


@pytest.mark.asyncio
async def test_get_giveaways_error(steamgifts_client):
    """Test get_giveaways raises error on HTTP error."""
    mock_response = MagicMock()
    mock_response.status_code = 500

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    steamgifts_client._client = mock_client

    with pytest.raises(SteamGiftsError, match="Failed to fetch giveaways"):
        await steamgifts_client.get_giveaways()


@pytest.mark.asyncio
async def test_parse_giveaway_element_success(steamgifts_client):
    """Test parsing giveaway element from HTML."""
    from bs4 import BeautifulSoup

    html = """
    <div class="giveaway__row-inner-wrap">
        <a href="/giveaway/XyZ99/awesome-game" class="giveaway__heading__name">Awesome Game</a>
        <span class="giveaway__heading__thin">(75P)</span>
        <span class="giveaway__links">250 entries</span>
        <span data-timestamp="1640000000"></span>
        <a class="giveaway_image_thumbnail" style="background-image:url('https://cdn.akamai.steamstatic.com/steam/apps/123456/header.jpg')"></a>
    </div>
    """

    soup = BeautifulSoup(html, "html.parser")
    element = soup.find("div", class_="giveaway__row-inner-wrap")

    result = steamgifts_client._parse_giveaway_element(element)

    assert result is not None
    assert result["code"] == "XyZ99"
    assert result["game_name"] == "Awesome Game"
    assert result["price"] == 75
    assert result["entries"] == 250
    assert result["game_id"] == 123456
    assert isinstance(result["end_time"], datetime)


@pytest.mark.asyncio
async def test_parse_giveaway_element_missing_link(steamgifts_client):
    """Test parsing returns None when required elements missing."""
    from bs4 import BeautifulSoup

    html = """
    <div class="giveaway__row-inner-wrap">
        <span>No link here</span>
    </div>
    """

    soup = BeautifulSoup(html, "html.parser")
    element = soup.find("div", class_="giveaway__row-inner-wrap")

    result = steamgifts_client._parse_giveaway_element(element)

    assert result is None


@pytest.mark.asyncio
async def test_enter_giveaway_success(steamgifts_client):
    """Test successfully entering a giveaway."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"type": "success"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    steamgifts_client._client = mock_client

    success = await steamgifts_client.enter_giveaway("AbCd1")

    assert success is True
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_enter_giveaway_failure(steamgifts_client):
    """Test entering giveaway returns False on error."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"type": "error", "msg": "Not enough points"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    steamgifts_client._client = mock_client

    success = await steamgifts_client.enter_giveaway("AbCd1")

    assert success is False


@pytest.mark.asyncio
async def test_enter_giveaway_http_error(steamgifts_client):
    """Test enter_giveaway raises error on HTTP error."""
    mock_response = MagicMock()
    mock_response.status_code = 500

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    steamgifts_client._client = mock_client

    with pytest.raises(SteamGiftsError, match="Failed to enter giveaway"):
        await steamgifts_client.enter_giveaway("AbCd1")


@pytest.mark.asyncio
async def test_enter_giveaway_refreshes_token_if_needed(steamgifts_client):
    """Test enter_giveaway refreshes XSRF token if not set."""
    steamgifts_client.xsrf_token = None
    steamgifts_client._refresh_xsrf_token = AsyncMock()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"type": "success"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    steamgifts_client._client = mock_client

    await steamgifts_client.enter_giveaway("AbCd1")

    # Should have refreshed token
    steamgifts_client._refresh_xsrf_token.assert_called_once()


@pytest.mark.asyncio
async def test_get_giveaway_details_success(steamgifts_client):
    """Test fetching giveaway details."""
    mock_html = """
    <html>
        <body>
            <a class="giveaway__heading__name">Portal 2</a>
        </body>
    </html>
    """

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_html

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    steamgifts_client._client = mock_client

    details = await steamgifts_client.get_giveaway_details("AbCd1")

    assert details["code"] == "AbCd1"
    assert details["game_name"] == "Portal 2"


@pytest.mark.asyncio
async def test_get_giveaway_details_not_found(steamgifts_client):
    """Test get_giveaway_details raises error on 404."""
    mock_response = MagicMock()
    mock_response.status_code = 404

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    steamgifts_client._client = mock_client

    with pytest.raises(SteamGiftsNotFoundError, match="Giveaway not found"):
        await steamgifts_client.get_giveaway_details("InvalidCode")


@pytest.mark.asyncio
async def test_check_if_entered_placeholder(steamgifts_client):
    """Test check_if_entered (placeholder implementation)."""
    # Currently returns False as placeholder
    result = await steamgifts_client.check_if_entered("AbCd1")

    assert result is False


@pytest.mark.asyncio
async def test_client_without_session_raises_error(steamgifts_client):
    """Test methods raise error if session not started."""
    with pytest.raises(RuntimeError, match="Client session not started"):
        await steamgifts_client.get_user_points()

    with pytest.raises(RuntimeError, match="Client session not started"):
        await steamgifts_client.get_giveaways()

    with pytest.raises(RuntimeError, match="Client session not started"):
        await steamgifts_client.enter_giveaway("AbCd1")


# ==================== Safety Detection Tests ====================

class TestSafetyDetection:
    """Tests for trap/scam detection functionality."""

    def test_check_page_safety_clean_page(self, steamgifts_client):
        """Test check_page_safety returns safe for clean pages."""
        clean_html = """
        <html>
            <body>
                <div class="giveaway">
                    <h2>Portal 2 Giveaway</h2>
                    <p>Enjoy this great game!</p>
                </div>
            </body>
        </html>
        """

        result = steamgifts_client.check_page_safety(clean_html)

        assert result["is_safe"] is True
        assert result["safety_score"] == 100
        assert result["bad_count"] == 0
        assert result["good_count"] == 0
        assert result["details"] == []

    def test_check_page_safety_with_forbidden_words(self, steamgifts_client):
        """Test check_page_safety detects forbidden words."""
        unsafe_html = """
        <html>
            <body>
                <div class="giveaway">
                    <h2>Test Giveaway</h2>
                    <p>Warning: don't enter this giveaway, it's fake!</p>
                    <p>You will get a ban if you enter.</p>
                </div>
            </body>
        </html>
        """

        result = steamgifts_client.check_page_safety(unsafe_html)

        assert result["is_safe"] is False
        assert result["safety_score"] < 100
        assert result["bad_count"] >= 3  # "don't enter", "fake", "ban"
        assert len(result["details"]) > 0
        assert any("ban" in word for word in result["details"])

    def test_check_page_safety_with_false_positives(self, steamgifts_client):
        """Test check_page_safety handles false positives correctly."""
        # Contains "ban" but in context of "bank" or "banner"
        tricky_html = """
        <html>
            <body>
                <div class="giveaway">
                    <h2>Bank Heist Simulator</h2>
                    <p>Rob the bank and escape!</p>
                    <p>See the banner above for details.</p>
                </div>
            </body>
        </html>
        """

        result = steamgifts_client.check_page_safety(tricky_html)

        # Should be safe because "bank" and "banner" are in good words list
        assert result["is_safe"] is True
        assert result["good_count"] >= result["bad_count"]  # Good words cancel out

    def test_check_page_safety_borderline(self, steamgifts_client):
        """Test check_page_safety with borderline content."""
        # Only one suspicious word - might be false positive
        borderline_html = """
        <html>
            <body>
                <div class="giveaway">
                    <h2>Cool Game</h2>
                    <p>This is totally not a bot giveaway!</p>
                </div>
            </body>
        </html>
        """

        result = steamgifts_client.check_page_safety(borderline_html)

        # Should have detected "bot" and possibly "not" context
        assert result["bad_count"] >= 1
        # With only 1-2 bad words, should still be allowed (borderline)
        assert result["safety_score"] >= 50

    @pytest.mark.asyncio
    async def test_check_giveaway_safety_success(self, steamgifts_client):
        """Test check_giveaway_safety fetches and checks page."""
        mock_html = """
        <html>
            <body>
                <div class="giveaway">
                    <h2>Safe Giveaway</h2>
                    <p>No suspicious content here.</p>
                </div>
            </body>
        </html>
        """

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = mock_html

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        steamgifts_client._client = mock_client

        result = await steamgifts_client.check_giveaway_safety("AbCd1")

        assert result["is_safe"] is True
        assert result["safety_score"] == 100
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_giveaway_safety_not_found(self, steamgifts_client):
        """Test check_giveaway_safety raises error for 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        steamgifts_client._client = mock_client

        with pytest.raises(SteamGiftsNotFoundError, match="Giveaway not found"):
            await steamgifts_client.check_giveaway_safety("InvalidCode")


# ==================== Hide Giveaway Tests ====================

class TestHideGiveaway:
    """Tests for hide giveaway functionality."""

    @pytest.mark.asyncio
    async def test_hide_giveaway_success(self, steamgifts_client):
        """Test hide_giveaway posts to ajax endpoint."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        steamgifts_client._client = mock_client

        result = await steamgifts_client.hide_giveaway(12345)

        assert result is True
        mock_client.post.assert_called_once()

        # Verify correct data was sent
        call_args = mock_client.post.call_args
        assert call_args[1]["data"]["do"] == "hide_giveaways_by_game_id"
        assert call_args[1]["data"]["game_id"] == 12345

    @pytest.mark.asyncio
    async def test_hide_giveaway_failure(self, steamgifts_client):
        """Test hide_giveaway raises error on HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        steamgifts_client._client = mock_client

        with pytest.raises(SteamGiftsError, match="Failed to hide giveaway"):
            await steamgifts_client.hide_giveaway(12345)

    @pytest.mark.asyncio
    async def test_hide_giveaway_refreshes_token(self, steamgifts_client):
        """Test hide_giveaway refreshes XSRF token if not set."""
        steamgifts_client.xsrf_token = None
        steamgifts_client._refresh_xsrf_token = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        steamgifts_client._client = mock_client

        await steamgifts_client.hide_giveaway(12345)

        steamgifts_client._refresh_xsrf_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_giveaway_game_id_success(self, steamgifts_client):
        """Test get_giveaway_game_id extracts game ID from page."""
        mock_html = """
        <html>
            <body>
                <div class="featured__outer-wrap" data-game-id="123456">
                    <h2>Game Title</h2>
                </div>
            </body>
        </html>
        """

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = mock_html

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        steamgifts_client._client = mock_client

        result = await steamgifts_client.get_giveaway_game_id("AbCd1")

        assert result == 123456

    @pytest.mark.asyncio
    async def test_get_giveaway_game_id_not_found(self, steamgifts_client):
        """Test get_giveaway_game_id returns None when game ID not found."""
        mock_html = """
        <html>
            <body>
                <div class="some-other-class">
                    <h2>No game ID here</h2>
                </div>
            </body>
        </html>
        """

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = mock_html

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        steamgifts_client._client = mock_client

        result = await steamgifts_client.get_giveaway_game_id("AbCd1")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_giveaway_game_id_http_error(self, steamgifts_client):
        """Test get_giveaway_game_id returns None on HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        steamgifts_client._client = mock_client

        result = await steamgifts_client.get_giveaway_game_id("InvalidCode")

        assert result is None


# ==================== DLC Scanning Tests ====================

class TestDLCScanning:
    """Tests for DLC-specific giveaway scanning."""

    @pytest.mark.asyncio
    async def test_get_giveaways_dlc_only(self, steamgifts_client):
        """Test get_giveaways with dlc_only parameter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body></body></html>"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        steamgifts_client._client = mock_client

        await steamgifts_client.get_giveaways(page=1, dlc_only=True)

        # Verify dlc=true was passed in params
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["dlc"] == "true"

    @pytest.mark.asyncio
    async def test_get_giveaways_min_copies(self, steamgifts_client):
        """Test get_giveaways with min_copies parameter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body></body></html>"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        steamgifts_client._client = mock_client

        await steamgifts_client.get_giveaways(page=1, min_copies=5)

        # Verify copy_min was passed in params
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["copy_min"] == "5"

    @pytest.mark.asyncio
    async def test_get_giveaways_dlc_and_min_copies(self, steamgifts_client):
        """Test get_giveaways with both dlc_only and min_copies."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body></body></html>"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        steamgifts_client._client = mock_client

        await steamgifts_client.get_giveaways(
            page=2,
            dlc_only=True,
            min_copies=10,
            giveaway_type="wishlist"
        )

        # Verify all params were passed
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        params = call_args[1]["params"]
        assert params["dlc"] == "true"
        assert params["copy_min"] == "10"
        assert params["type"] == "wishlist"
        assert params["page"] == 2
