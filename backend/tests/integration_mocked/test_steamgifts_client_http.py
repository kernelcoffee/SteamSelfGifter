"""SteamGiftsClient against a mocked SteamGifts over real httpx plumbing.

These exercise what the unit tests (which stub _get/_post) cannot: cookie
and header wiring, query/form encoding, XSRF extraction on start, retry
and backoff behavior, and client+parser integration on captured fixtures.
"""

from urllib.parse import parse_qs

import httpx
import pytest

from utils.steamgifts_client import (
    SteamGiftsClient,
    SteamGiftsError,
    SteamGiftsScrapeDriftError,
    SteamGiftsSessionExpiredError,
)

pytestmark = pytest.mark.asyncio

XSRF = "deadbeefdeadbeefdeadbeefdeadbeef"


def make_client(transport, **kwargs):
    kwargs.setdefault("phpsessid", "sess-abc")
    kwargs.setdefault("user_agent", "ua-test")
    kwargs.setdefault("xsrf_token", XSRF)
    return SteamGiftsClient(transport=transport, **kwargs)


class TestSessionSetup:
    async def test_start_extracts_xsrf_and_sends_cookie(self, transport, wishlist_html):
        transport.add("GET", "/", httpx.Response(200, text=wishlist_html))

        async with make_client(transport, xsrf_token=None) as client:
            assert client.xsrf_token == XSRF

        [request] = transport.requests
        assert request.headers["Cookie"] == "PHPSESSID=sess-abc"
        assert request.headers["User-Agent"] == "ua-test"

    async def test_start_without_xsrf_on_page_raises_session_expired(self, transport):
        transport.add("GET", "/", httpx.Response(200, text="<html><body></body></html>"))

        client = make_client(transport, xsrf_token=None)
        with pytest.raises(SteamGiftsSessionExpiredError):
            await client.start()
        await client.close()

    async def test_get_user_points(self, transport, wishlist_html):
        transport.add("GET", "/", httpx.Response(200, text=wishlist_html))

        async with make_client(transport) as client:
            assert await client.get_user_points() == 400


class TestGiveawayListing:
    async def test_wishlist_scan_parses_fixture(self, transport, wishlist_html):
        transport.add("GET", "/giveaways/search", httpx.Response(200, text=wishlist_html))

        async with make_client(transport) as client:
            giveaways = await client.get_giveaways(page=2, giveaway_type="wishlist")

        [ga] = giveaways
        assert ga["code"] == "hVTVd"
        assert ga["game_name"] == "Tomb Raider IV-VI Remastered"
        assert ga["price"] == 30
        assert ga["is_wishlist"] is True
        assert ga["entries"] == 455

        [request] = transport.requests
        assert request.url.params["page"] == "2"
        assert request.url.params["type"] == "wishlist"

    async def test_dlc_scan_sends_dlc_param(self, transport, wishlist_html):
        transport.add("GET", "/giveaways/search", httpx.Response(200, text=wishlist_html))

        async with make_client(transport) as client:
            giveaways = await client.get_giveaways(dlc_only=True)

        assert giveaways[0]["is_dlc"] is True
        [request] = transport.requests
        assert request.url.params["dlc"] == "true"

    async def test_empty_search_returns_empty_list(self, transport, empty_search_html):
        transport.add("GET", "/giveaways/search", httpx.Response(200, text=empty_search_html))

        async with make_client(transport) as client:
            assert await client.get_giveaways(search_query="nonexistent") == []

    async def test_unrecognizable_page_raises_drift_error(self, transport):
        transport.add(
            "GET", "/giveaways/search", httpx.Response(200, text="<html><body>hi</body></html>")
        )

        async with make_client(transport) as client:
            with pytest.raises(SteamGiftsScrapeDriftError):
                await client.get_giveaways()


class TestEnterGiveaway:
    async def test_success_posts_xsrf_form(self, transport):
        transport.add("POST", "/ajax.php", httpx.Response(200, json={"type": "success"}))

        async with make_client(transport) as client:
            assert await client.enter_giveaway("hVTVd") is True

        [request] = transport.requests
        form = parse_qs(request.content.decode())
        assert form == {
            "xsrf_token": [XSRF],
            "do": ["entry_insert"],
            "code": ["hVTVd"],
        }
        assert request.headers["Content-Type"] == "application/x-www-form-urlencoded"

    async def test_rejection_returns_false(self, transport):
        transport.add(
            "POST",
            "/ajax.php",
            httpx.Response(200, json={"type": "error", "msg": "Not enough points"}),
        )

        async with make_client(transport) as client:
            assert await client.enter_giveaway("hVTVd") is False


class TestRetries:
    async def test_get_retries_5xx_then_succeeds(self, transport, wishlist_html, no_sleep):
        transport.add(
            "GET",
            "/",
            httpx.Response(500),
            httpx.Response(502),
            httpx.Response(200, text=wishlist_html),
        )

        async with make_client(transport) as client:
            assert await client.get_user_points() == 400

        assert len(transport.requests) == 3

    async def test_get_honors_retry_after_on_429(self, transport, wishlist_html, no_sleep):
        transport.add(
            "GET",
            "/",
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, text=wishlist_html),
        )

        async with make_client(transport) as client:
            assert await client.get_user_points() == 400

        no_sleep.assert_awaited_once_with(7.0)

    async def test_get_gives_up_after_max_retries(self, transport, no_sleep):
        transport.add("GET", "/giveaways/search", httpx.Response(500))

        async with make_client(transport, max_retries=1) as client:
            with pytest.raises(SteamGiftsError):
                await client.get_giveaways()

        assert len(transport.requests) == 2

    async def test_connect_errors_retried_then_wrapped(self, no_sleep):
        attempts = 0

        class FailingTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                nonlocal attempts
                attempts += 1
                raise httpx.ConnectError("connection refused")

        async with make_client(FailingTransport(), max_retries=1) as client:
            with pytest.raises(SteamGiftsError):
                await client.get_user_points()

        assert attempts == 2
