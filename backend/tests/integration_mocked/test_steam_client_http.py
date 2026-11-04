"""SteamClient against mocked Steam APIs over real httpx plumbing."""

import json

import httpx
import pytest
import structlog

from utils.steam_client import (
    MAX_REVIEW_COUNT,
    SteamAPIError,
    SteamAPINotFoundError,
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
        # Language pinned so genre/category names never localize.
        assert request.url.params["l"] == "english"

    async def test_unsuccessful_lookup_returns_none(self, transport):
        transport.add(
            "GET", "/api/appdetails", httpx.Response(200, json={"999": {"success": False}})
        )

        async with SteamClient(transport=transport) as client:
            assert await client.get_app_details(999) is None

    async def test_null_body_raises_rate_limit_error(self, transport):
        """A throttled store API can answer 200 with the body `null`: that is a
        rate-limit error the callers handle, not an AttributeError."""
        transport.add("GET", "/api/appdetails", httpx.Response(200, content=b"null"))

        async with SteamClient(transport=transport) as client:
            with pytest.raises(SteamAPIRateLimitError):
                await client.get_app_details(2525380)

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


REVIEWS_PATH = "/IUserReviewsService/GetAppReviews/v1/"
REVIEWS_BODY = {
    "response": {
        "query_summary": {
            "num_reviews": 1,
            "review_score": 8,
            "review_score_desc": "Very Positive",
            "total_positive": 900,
            "total_negative": 100,
            "total_reviews": 1000,
        },
        "reviews": [{"recommendationid": "1", "voted_up": True}],
    }
}


class TestAppReviews:
    async def test_success_parses_summary_from_get_app_reviews(self, transport):
        """GetAppReviews is public: even with a configured key, none is sent."""
        transport.add("GET", REVIEWS_PATH, httpx.Response(200, json=REVIEWS_BODY))

        async with SteamClient(api_key="SECRETKEY", transport=transport) as client:
            reviews = await client.get_app_reviews(2525380)

        assert reviews == {
            "review_score": 8,
            "total_positive": 900,
            "total_negative": 100,
            "total_reviews": 1000,
        }
        [request] = transport.requests
        assert request.method == "GET"
        assert request.url.scheme == "https"
        assert request.url.host == "api.steampowered.com"
        assert request.url.path == REVIEWS_PATH
        # Only input_json, holding the API defaults (D2): no key, no
        # languages or purchase_type override.
        assert list(request.url.params.keys()) == ["input_json"]
        assert json.loads(request.url.params["input_json"]) == {"appid": 2525380, "num_per_page": 1}
        assert "SECRETKEY" not in str(request.url)
        assert "cookie" not in request.headers
        assert "referer" not in request.headers

    async def test_missing_summary_field_counts_as_zero(self, transport):
        body = {"response": {"query_summary": {"review_score": 5, "total_positive": 40, "total_reviews": 40}}}
        transport.add("GET", REVIEWS_PATH, httpx.Response(200, json=body))

        async with SteamClient(transport=transport) as client:
            reviews = await client.get_app_reviews(2525380)

        assert reviews == {
            "review_score": 5,
            "total_positive": 40,
            "total_negative": 0,
            "total_reviews": 40,
        }

    @pytest.mark.parametrize(
        "body",
        [
            {"response": {}},
            {"response": "x"},
            {"response": {"query_summary": "x"}},
            {},
            [],
        ],
        ids=["unknown-app", "response-not-object", "summary-not-object", "no-response", "body-not-object"],
    )
    async def test_no_summary_returns_none(self, transport, body):
        """A 200 without a query_summary is "no reviews", never an exception."""
        transport.add("GET", REVIEWS_PATH, httpx.Response(200, json=body))

        async with SteamClient(transport=transport) as client:
            with structlog.testing.capture_logs() as logs:
                assert await client.get_app_reviews(999999999) is None

        assert len(transport.requests) == 1
        assert {"event": "review_api_no_data", "app_id": 999999999, "log_level": "warning"} in logs

    @pytest.mark.parametrize("status", [302, 301, 403, 400])
    async def test_non_200_raises_steam_api_error(self, transport, status):
        """A redirect (what the deprecated endpoint answered) or a refusal is a
        failure the game service keeps cached data through, not "no reviews"."""
        headers = {"location": "https://store.steampowered.com/"} if status in (301, 302) else {}
        transport.add("GET", REVIEWS_PATH, httpx.Response(status, headers=headers))

        async with SteamClient(transport=transport) as client:
            with pytest.raises(SteamAPIError) as exc_info:
                await client.get_app_reviews(2525380)

        assert type(exc_info.value) is SteamAPIError
        # The redirect is not followed anywhere.
        assert len(transport.requests) == 1

    async def test_404_raises_not_found(self, transport):
        transport.add("GET", REVIEWS_PATH, httpx.Response(404))

        async with SteamClient(transport=transport) as client:
            with pytest.raises(SteamAPINotFoundError):
                await client.get_app_reviews(2525380)

        assert len(transport.requests) == 1

    async def test_429_raises_rate_limit_error_without_retry(self, transport, no_sleep):
        transport.add("GET", REVIEWS_PATH, httpx.Response(429))

        async with SteamClient(transport=transport) as client:
            with pytest.raises(SteamAPIRateLimitError):
                await client.get_app_reviews(2525380)

        assert len(transport.requests) == 1
        no_sleep.assert_not_called()

    async def test_5xx_gives_up_after_bounded_retries(self, transport, no_sleep):
        transport.add("GET", REVIEWS_PATH, httpx.Response(500))

        async with SteamClient(transport=transport) as client:
            with pytest.raises(SteamAPIError):
                await client.get_app_reviews(2525380)

        # One request plus max_retries (3) retries with exponential backoff.
        assert len(transport.requests) == 4
        assert [call.args[0] for call in no_sleep.call_args_list] == [1, 2, 4]

    async def test_invalid_json_raises_steam_api_error(self, transport):
        transport.add(
            "GET", REVIEWS_PATH, httpx.Response(200, content=b"<html>not json</html>")
        )

        async with SteamClient(transport=transport) as client:
            with pytest.raises(SteamAPIError, match="invalid JSON"):
                await client.get_app_reviews(2525380)

        assert len(transport.requests) == 1

    @pytest.mark.parametrize(
        "value", [None, "lots", "8", [1], 8.0], ids=["null", "text", "numeric-text", "list", "float"]
    )
    async def test_non_numeric_summary_field_raises_steam_api_error(self, transport, value):
        """Hostile JSON in the summary is a failed fetch, not a TypeError."""
        body = {"response": {"query_summary": {"review_score": 8, "total_reviews": value}}}
        transport.add("GET", REVIEWS_PATH, httpx.Response(200, json=body))

        async with SteamClient(transport=transport) as client:
            with pytest.raises(SteamAPIError, match="malformed query_summary"):
                await client.get_app_reviews(2525380)


class TestAppReviewsHostileSummary:
    """Steam JSON is hostile input: the parser raises its documented
    SteamAPIError, and bounds what it returns to what the non-nullable
    INTEGER columns and the 0-9 score scale hold."""

    @pytest.mark.parametrize(
        "value",
        [float("inf"), float("-inf")],
        ids=["Infinity", "-Infinity"],
    )
    async def test_non_finite_summary_field_raises_steam_api_error(self, transport, value):
        # json.loads accepts the bare Infinity token; int(inf) would raise
        # OverflowError instead of the documented SteamAPIError.
        body = {"response": {"query_summary": {"review_score": 8, "total_positive": value}}}
        transport.add("GET", REVIEWS_PATH, httpx.Response(200, content=json.dumps(body).encode()))

        async with SteamClient(transport=transport) as client:
            with pytest.raises(SteamAPIError, match="malformed query_summary"):
                await client.get_app_reviews(2525380)

    @pytest.mark.parametrize(
        "summary",
        [
            {"review_score": 8, "total_positive": 10**20, "total_negative": 0},
            {"review_score": 8, "total_positive": -1000, "total_negative": 0},
            {"review_score": 100, "total_positive": 10, "total_negative": 0},
            {"review_score": True, "total_positive": 10, "total_negative": 0},
        ],
        ids=["beyond-sqlite-int64", "negative-count", "score-off-scale", "bool-score"],
    )
    async def test_out_of_range_summary_field_raises_steam_api_error(self, transport, summary):
        # 10**20 would fail at commit with OverflowError (outside every
        # except in _fetch_from_steam), poisoning the sync session; a score
        # of 100 would pass any autojoin_min_score.
        body = {"response": {"query_summary": summary}}
        transport.add("GET", REVIEWS_PATH, httpx.Response(200, json=body))

        async with SteamClient(transport=transport) as client:
            with pytest.raises(SteamAPIError, match="malformed query_summary"):
                await client.get_app_reviews(2525380)

    async def test_values_at_the_bounds_are_accepted(self, transport):
        """The largest score (9) and count (MAX_REVIEW_COUNT) and zeros pass."""
        summary = {
            "review_score": 9,
            "total_positive": MAX_REVIEW_COUNT,
            "total_negative": 0,
            "total_reviews": MAX_REVIEW_COUNT,
        }
        transport.add("GET", REVIEWS_PATH, httpx.Response(200, json={"response": {"query_summary": summary}}))

        async with SteamClient(transport=transport) as client:
            assert await client.get_app_reviews(2525380) == summary

    @pytest.mark.parametrize("field", ["total_positive", "total_negative", "total_reviews"])
    async def test_count_above_the_bound_raises_steam_api_error(self, transport, field):
        summary = {"review_score": 8, field: MAX_REVIEW_COUNT + 1}
        transport.add("GET", REVIEWS_PATH, httpx.Response(200, json={"response": {"query_summary": summary}}))

        async with SteamClient(transport=transport) as client:
            with pytest.raises(SteamAPIError, match=rf"malformed query_summary \({field}\)"):
                await client.get_app_reviews(2525380)


class TestAppReviewsBoundaries:
    @pytest.mark.parametrize("score", [10, -1], ids=["just-above-9", "negative"])
    async def test_score_just_outside_the_scale_raises_steam_api_error(self, transport, score):
        """review_score is Steam's 0-9 bucket: the first value past either end is rejected."""
        summary = {"review_score": score, "total_positive": 10, "total_negative": 0, "total_reviews": 10}
        transport.add("GET", REVIEWS_PATH, httpx.Response(200, json={"response": {"query_summary": summary}}))

        async with SteamClient(transport=transport) as client:
            with pytest.raises(SteamAPIError, match=r"malformed query_summary \(review_score\)"):
                await client.get_app_reviews(2525380)

    async def test_all_zero_summary_is_accepted(self, transport):
        """A game with fewer than ten reviews: score 0 and zero counts are data, not an error."""
        summary = {"review_score": 0, "total_positive": 0, "total_negative": 0, "total_reviews": 0}
        transport.add("GET", REVIEWS_PATH, httpx.Response(200, json={"response": {"query_summary": summary}}))

        async with SteamClient(transport=transport) as client:
            assert await client.get_app_reviews(2525380) == summary

    async def test_network_error_is_retried_then_raises_steam_api_error(self, no_sleep):
        """A connection failure is retried with the bounded backoff and then
        raised as SteamAPIError, never swallowed into None."""
        attempts: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempts.append(request)
            raise httpx.ConnectError("connection refused", request=request)

        async with SteamClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(SteamAPIError, match="Network error"):
                await client.get_app_reviews(2525380)

        assert len(attempts) == 4
        assert all(r.url.path == REVIEWS_PATH for r in attempts)
        assert [call.args[0] for call in no_sleep.call_args_list] == [1, 2, 4]
