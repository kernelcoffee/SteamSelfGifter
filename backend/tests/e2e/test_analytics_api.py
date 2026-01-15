"""End-to-end tests for analytics API endpoints.

Note: Many analytics endpoints require GiveawayServiceDep which creates a
SteamGiftsClient that attempts to authenticate with SteamGifts.com.
These endpoints need proper mocking in integration tests.

This file tests the endpoints that work without external API access.
"""

import pytest
from httpx import AsyncClient


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


# Note: The following analytics endpoints require GiveawayServiceDep which
# creates a SteamGiftsClient that attempts external authentication:
# - GET /api/v1/analytics/overview
# - GET /api/v1/analytics/entries/summary
# - GET /api/v1/analytics/giveaways/summary
# - GET /api/v1/analytics/scheduler/summary
# - GET /api/v1/analytics/points
# - GET /api/v1/analytics/recent-activity
# - GET /api/v1/analytics/dashboard
#
# These endpoints are tested in integration tests with proper mocking of
# the SteamGiftsClient dependency.
