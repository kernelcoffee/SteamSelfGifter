"""SteamClient against mocked Steam APIs over real httpx plumbing."""

import httpx
import pytest

from utils.steam_client import (
    SteamAPIError,
    SteamAPIRateLimitError,
    SteamClient,
)

pytestmark = pytest.mark.asyncio

APP_DETAILS = {
    "2525380": {
        "success": True,
        "data": {
            "name": "Tomb Raider IV-VI Remastered",
            "type": "game",
            "steam_appid": 2525380,
        },
    }
}


class TestAppDetails:
    async def test_success_parses_payload(self, transport):
        transport.add("GET", "/api/appdetails", httpx.Response(200, json=APP_DETAILS))

        async with SteamClient(transport=transport) as client:
            details = await client.get_app_details(2525380)

        assert details == APP_DETAILS["2525380"]["data"]
        [request] = transport.requests
        assert request.url.host == "store.steampowered.com"
        assert request.url.params["appids"] == "2525380"

    async def test_unsuccessful_lookup_returns_none(self, transport):
        transport.add(
            "GET", "/api/appdetails", httpx.Response(200, json={"999": {"success": False}})
        )

        async with SteamClient(transport=transport) as client:
            assert await client.get_app_details(999) is None

    async def test_404_returns_none(self, transport):
        transport.add("GET", "/api/appdetails", httpx.Response(404))

        async with SteamClient(transport=transport) as client:
            assert await client.get_app_details(999) is None

    async def test_429_raises_rate_limit_error(self, transport):
        transport.add("GET", "/api/appdetails", httpx.Response(429))

        async with SteamClient(transport=transport) as client:
            with pytest.raises(SteamAPIRateLimitError):
                await client.get_app_details(2525380)

    async def test_5xx_retried_then_succeeds(self, transport, no_sleep):
        transport.add(
            "GET",
            "/api/appdetails",
            httpx.Response(500),
            httpx.Response(503),
            httpx.Response(200, json=APP_DETAILS),
        )

        async with SteamClient(transport=transport) as client:
            details = await client.get_app_details(2525380)

        assert details is not None
        assert len(transport.requests) == 3

    async def test_5xx_gives_up_after_max_retries(self, transport, no_sleep):
        transport.add("GET", "/api/appdetails", httpx.Response(500))

        async with SteamClient(transport=transport, max_retries=1) as client:
            with pytest.raises(SteamAPIError):
                await client.get_app_details(2525380)

        assert len(transport.requests) == 2


class TestAppReviews:
    async def test_success_parses_summary(self, transport):
        transport.add(
            "GET",
            "/appreviews/2525380",
            httpx.Response(
                200,
                json={
                    "success": 1,
                    "query_summary": {
                        "review_score": 9,
                        "total_positive": 900,
                        "total_negative": 100,
                        "total_reviews": 1000,
                    },
                },
            ),
        )

        async with SteamClient(transport=transport) as client:
            reviews = await client.get_app_reviews(2525380)

        assert reviews == {
            "review_score": 9,
            "total_positive": 900,
            "total_negative": 100,
            "total_reviews": 1000,
        }
        [request] = transport.requests
        assert request.url.params["json"] == "1"

    async def test_non_200_returns_none(self, transport):
        transport.add("GET", "/appreviews/2525380", httpx.Response(403))

        async with SteamClient(transport=transport) as client:
            assert await client.get_app_reviews(2525380) is None
