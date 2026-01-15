"""Unit tests for SteamClient."""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
import httpx

from utils.steam_client import (
    SteamClient,
    RateLimiter,
    SteamAPIError,
    SteamAPIRateLimitError,
    SteamAPINotFoundError,
)


# RateLimiter Tests


@pytest.mark.asyncio
async def test_rate_limiter_allows_calls_within_limit():
    """Test rate limiter allows calls within limit."""
    limiter = RateLimiter(max_calls=3, window_seconds=1)

    # Should allow 3 calls immediately
    for _ in range(3):
        async with limiter:
            pass  # Call allowed


@pytest.mark.asyncio
async def test_rate_limiter_blocks_when_limit_exceeded():
    """Test rate limiter blocks calls when limit exceeded."""
    limiter = RateLimiter(max_calls=2, window_seconds=1)

    start = datetime.utcnow()

    # First 2 calls should be instant
    for _ in range(2):
        async with limiter:
            pass

    # Third call should be delayed until window expires
    async with limiter:
        pass

    elapsed = (datetime.utcnow() - start).total_seconds()

    # Should have waited ~1 second
    assert elapsed >= 0.9  # Allow small timing variance


@pytest.mark.asyncio
async def test_rate_limiter_sliding_window():
    """Test rate limiter uses sliding window correctly."""
    limiter = RateLimiter(max_calls=2, window_seconds=2)

    # Make 2 calls
    async with limiter:
        pass
    async with limiter:
        pass

    # Wait half window
    await asyncio.sleep(1)

    # Old calls still in window, should block
    start = datetime.utcnow()
    async with limiter:
        pass
    elapsed = (datetime.utcnow() - start).total_seconds()

    assert elapsed >= 0.9  # Should wait ~1 more second


# SteamClient Tests


@pytest.fixture
def steam_client():
    """Create SteamClient instance."""
    client = SteamClient(
        api_key="test_key",
        rate_limit_calls=100,
        rate_limit_window=60,
        max_retries=3,
        timeout_seconds=30,
    )
    return client


@pytest.mark.asyncio
async def test_steam_client_init():
    """Test SteamClient initialization."""
    client = SteamClient(
        api_key="test_key",
        rate_limit_calls=50,
        rate_limit_window=30,
    )

    assert client.api_key == "test_key"
    assert client.max_retries == 3
    assert client.rate_limiter.max_calls == 50
    assert client._client is None


@pytest.mark.asyncio
async def test_steam_client_start_creates_session(steam_client):
    """Test start() creates httpx client."""
    await steam_client.start()

    assert steam_client._client is not None
    assert isinstance(steam_client._client, httpx.AsyncClient)

    await steam_client.close()


@pytest.mark.asyncio
async def test_steam_client_close_cleans_session(steam_client):
    """Test close() cleans up session."""
    await steam_client.start()
    assert steam_client._client is not None

    await steam_client.close()
    assert steam_client._client is None


@pytest.mark.asyncio
async def test_steam_client_context_manager(steam_client):
    """Test SteamClient works as async context manager."""
    async with steam_client as client:
        assert client._client is not None

    # Client should be closed after context
    assert steam_client._client is None


@pytest.mark.asyncio
async def test_request_without_session_raises_error(steam_client):
    """Test _request() raises error if session not started."""
    with pytest.raises(RuntimeError, match="Client session not started"):
        await steam_client._request("https://example.com")


@pytest.mark.asyncio
async def test_request_success(steam_client):
    """Test successful API request."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True, "data": "test"}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    steam_client._client = mock_client

    result = await steam_client._request("https://example.com", params={"test": "1"})

    assert result == {"success": True, "data": "test"}
    mock_client.get.assert_called_once_with("https://example.com", params={"test": "1"})


@pytest.mark.asyncio
async def test_request_404_raises_not_found(steam_client):
    """Test 404 response raises SteamAPINotFoundError."""
    mock_response = MagicMock()
    mock_response.status_code = 404

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    steam_client._client = mock_client

    with pytest.raises(SteamAPINotFoundError, match="Resource not found"):
        await steam_client._request("https://example.com")


@pytest.mark.asyncio
async def test_request_429_raises_rate_limit(steam_client):
    """Test 429 response raises SteamAPIRateLimitError."""
    mock_response = MagicMock()
    mock_response.status_code = 429

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    steam_client._client = mock_client

    with pytest.raises(SteamAPIRateLimitError, match="rate limit exceeded"):
        await steam_client._request("https://example.com")


@pytest.mark.asyncio
async def test_request_500_retries(steam_client):
    """Test 500 error triggers retry with exponential backoff."""
    # First 2 calls fail with 500, third succeeds
    mock_response_fail = MagicMock()
    mock_response_fail.status_code = 500

    mock_response_success = MagicMock()
    mock_response_success.status_code = 200
    mock_response_success.json.return_value = {"success": True}

    mock_client = AsyncMock()
    # First 2 calls return 500, third returns 200
    mock_client.get = AsyncMock(
        side_effect=[mock_response_fail, mock_response_fail, mock_response_success]
    )

    steam_client._client = mock_client
    steam_client.max_retries = 3

    start = datetime.utcnow()
    result = await steam_client._request("https://example.com")
    elapsed = (datetime.utcnow() - start).total_seconds()

    assert result == {"success": True}
    # Should have waited 1s + 2s = 3s for exponential backoff
    assert elapsed >= 2.9


@pytest.mark.asyncio
async def test_request_500_exceeds_retries(steam_client):
    """Test 500 error exceeding max retries raises error."""
    mock_response = MagicMock()
    mock_response.status_code = 500

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    steam_client._client = mock_client
    steam_client.max_retries = 2

    with pytest.raises(SteamAPIError, match="server error: 500"):
        await steam_client._request("https://example.com")


@pytest.mark.asyncio
async def test_request_network_error_retries(steam_client):
    """Test network error triggers retry."""
    mock_client = AsyncMock()

    # First 2 calls fail with network error, third succeeds
    mock_response_success = MagicMock()
    mock_response_success.status_code = 200
    mock_response_success.json.return_value = {"success": True}

    mock_client.get = AsyncMock(
        side_effect=[
            httpx.ConnectError("Network error"),
            httpx.ConnectError("Network error"),
            mock_response_success,
        ]
    )

    steam_client._client = mock_client
    steam_client.max_retries = 3

    result = await steam_client._request("https://example.com")

    assert result == {"success": True}


@pytest.mark.asyncio
async def test_get_app_details_success(steam_client):
    """Test get_app_details() with successful response."""
    mock_data = {
        "730": {
            "success": True,
            "data": {
                "name": "Counter-Strike: Global Offensive",
                "type": "game",
                "steam_appid": 730,
            },
        }
    }

    steam_client._request = AsyncMock(return_value=mock_data)

    result = await steam_client.get_app_details(730)

    assert result["name"] == "Counter-Strike: Global Offensive"
    assert result["steam_appid"] == 730


@pytest.mark.asyncio
async def test_get_app_details_not_found(steam_client):
    """Test get_app_details() returns None when app not found."""
    mock_data = {"999999": {"success": False}}

    steam_client._request = AsyncMock(return_value=mock_data)

    result = await steam_client.get_app_details(999999)

    assert result is None


@pytest.mark.asyncio
async def test_get_app_details_api_error(steam_client):
    """Test get_app_details() returns None on API not found error."""
    steam_client._request = AsyncMock(side_effect=SteamAPINotFoundError("Not found"))

    result = await steam_client.get_app_details(730)

    assert result is None


@pytest.mark.asyncio
async def test_get_owned_games_success(steam_client):
    """Test get_owned_games() with successful response."""
    mock_data = {
        "response": {
            "game_count": 2,
            "games": [
                {"appid": 730, "name": "CS:GO", "playtime_forever": 1000},
                {"appid": 440, "name": "TF2", "playtime_forever": 500},
            ],
        }
    }

    steam_client._request = AsyncMock(return_value=mock_data)

    result = await steam_client.get_owned_games("76561197960434622")

    assert len(result) == 2
    assert result[0]["appid"] == 730
    assert result[1]["appid"] == 440


@pytest.mark.asyncio
async def test_get_owned_games_no_api_key():
    """Test get_owned_games() raises error without API key."""
    client = SteamClient(api_key=None)

    with pytest.raises(RuntimeError, match="Steam API key required"):
        await client.get_owned_games("76561197960434622")


@pytest.mark.asyncio
async def test_get_player_summary_success(steam_client):
    """Test get_player_summary() with successful response."""
    mock_data = {
        "response": {
            "players": [
                {
                    "steamid": "76561197960434622",
                    "personaname": "TestPlayer",
                    "profileurl": "https://steamcommunity.com/id/test/",
                }
            ]
        }
    }

    steam_client._request = AsyncMock(return_value=mock_data)

    result = await steam_client.get_player_summary("76561197960434622")

    assert result["steamid"] == "76561197960434622"
    assert result["personaname"] == "TestPlayer"


@pytest.mark.asyncio
async def test_get_player_summary_not_found(steam_client):
    """Test get_player_summary() returns None when player not found."""
    mock_data = {"response": {"players": []}}

    steam_client._request = AsyncMock(return_value=mock_data)

    result = await steam_client.get_player_summary("invalid_id")

    assert result is None


@pytest.mark.asyncio
async def test_get_player_summary_no_api_key():
    """Test get_player_summary() raises error without API key."""
    client = SteamClient(api_key=None)

    with pytest.raises(RuntimeError, match="Steam API key required"):
        await client.get_player_summary("76561197960434622")


@pytest.mark.asyncio
async def test_search_games_placeholder(steam_client):
    """Test search_games() returns empty list (placeholder)."""
    result = await steam_client.search_games("portal", max_results=5)

    # Currently a placeholder that returns empty list
    assert result == []


@pytest.mark.asyncio
async def test_rate_limiting_applied_to_requests(steam_client):
    """Test rate limiter is applied to all requests."""
    # Set very low rate limit
    steam_client.rate_limiter = RateLimiter(max_calls=2, window_seconds=1)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    steam_client._client = mock_client

    start = datetime.utcnow()

    # First 2 calls should be instant
    await steam_client._request("https://example.com")
    await steam_client._request("https://example.com")

    # Third call should wait
    await steam_client._request("https://example.com")

    elapsed = (datetime.utcnow() - start).total_seconds()

    # Should have rate limited the third call
    assert elapsed >= 0.9
