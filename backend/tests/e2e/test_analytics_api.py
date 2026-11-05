"""End-to-end tests for analytics API endpoints.

Note: Many analytics endpoints require GiveawayServiceDep which creates a
SteamGiftsClient that attempts to authenticate with SteamGifts.com.
These endpoints need proper mocking in integration tests.

This file tests the endpoints that work without external API access.
"""

import pytest
from httpx import AsyncClient

from utils.steam_client import SteamClient
from utils.steamgifts_client import SteamGiftsClient

# Analytics endpoints that require GiveawayServiceDep (external API) are tested
# in integration tests with mocking. Here we only test endpoints that work
# without external dependencies.


@pytest.mark.asyncio
async def test_get_game_summary(test_client: AsyncClient):
    """Test GET /api/v1/analytics/games/summary returns game cache stats."""
    response = await test_client.get("/api/v1/analytics/games/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    # Verify structure
    result = data["data"]
    assert "total_games" in result
    assert "games" in result
    assert "dlc" in result
    assert "bundles" in result
    assert "stale_games" in result


@pytest.mark.asyncio
async def test_game_summary_initial_state(test_client: AsyncClient):
    """Test game summary returns zeros for fresh database."""
    response = await test_client.get("/api/v1/analytics/games/summary")
    data = response.json()["data"]
    assert data["total_games"] == 0
    assert data["games"] == 0
    assert data["dlc"] == 0
    assert data["bundles"] == 0


@pytest.mark.asyncio
async def test_scheduler_summary_endpoint_starts_no_http_client(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test GET /api/v1/analytics/scheduler/summary starts no HTTP client:
    through FastAPI's dependency graph, SchedulerServiceDep resolves no
    SteamGifts or Steam client."""

    async def forbidden_start(self: object) -> None:
        raise AssertionError(f"{type(self).__name__}.start must not be called")

    monkeypatch.setattr(SteamClient, "start", forbidden_start)
    monkeypatch.setattr(SteamGiftsClient, "start", forbidden_start)

    response = await test_client.get("/api/v1/analytics/scheduler/summary")

    assert response.status_code == 200, response.text
    assert response.json()["success"] is True


# Note: The following analytics endpoints require GiveawayServiceDep which
# creates a SteamGiftsClient that attempts external authentication:
# - GET /api/v1/analytics/overview
# - GET /api/v1/analytics/entries/summary
# - GET /api/v1/analytics/giveaways/summary
# - GET /api/v1/analytics/points
# - GET /api/v1/analytics/recent-activity
# - GET /api/v1/analytics/dashboard
#
# These endpoints are tested in integration tests with proper mocking of
# the SteamGiftsClient dependency.
