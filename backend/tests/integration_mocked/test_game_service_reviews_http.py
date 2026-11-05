"""GameService over the real SteamClient and a mocked Steam transport.

The unit tests in tests/unit/test_services_game_service.py replace
``get_app_reviews`` with an AsyncMock, so they prove the service's branches
but not that what the real client raises for a given HTTP answer lands in
the right branch. These tests send real httpx requests through
RoutedTransport and assert the stored row, the reported status, the cool-down
and the requests sent.
"""

from datetime import timedelta

import httpx
import pytest

from core.time import utcnow
from repositories.game import STALE_AFTER_DAYS
from services.game_service import REVIEW_RETRY_DELAY, FetchStatus, GameService, steam_cooldown
from utils.steam_client import SteamClient

pytestmark = pytest.mark.asyncio

APP_ID = 367520
APPDETAILS_PATH = "/api/appdetails"
REVIEWS_PATH = "/IUserReviewsService/GetAppReviews/v1/"


def _appdetails(app_type: str = "game") -> dict:
    return {
        str(APP_ID): {
            "success": True,
            "data": {
                "type": app_type,
                "name": "Hollow Knight",
                "steam_appid": APP_ID,
                "genres": [{"id": "1", "description": "Action"}, {"id": "23", "description": "Indie"}],
                "categories": [{"id": 2, "description": "Single-player"}],
                "release_date": {"coming_soon": False, "date": "Feb 24, 2017"},
            },
        }
    }


def _summary(**fields: int) -> dict:
    return {"response": {"query_summary": fields, "reviews": []}}


def _paths(transport) -> list[str]:
    return [r.url.path for r in transport.requests]


async def _seed_cached(service: GameService, **overrides) -> None:
    values = {
        "id": APP_ID,
        "name": "Cached",
        "type": "game",
        "review_score": 8,
        "total_positive": 900,
        "total_negative": 100,
        "total_reviews": 1000,
        "genres": ["Action"],
        "last_refreshed_at": utcnow() - timedelta(days=30),
    }
    values.update(overrides)
    await service.repo.create(**values)
    await service.session.commit()


@pytest.mark.parametrize(
    "reviews_response",
    [
        httpx.Response(302, headers={"location": "https://store.steampowered.com/"}),
        httpx.Response(403),
        httpx.Response(404),
        httpx.Response(200, content=b"<html>maintenance</html>"),
        httpx.Response(200, json=_summary(review_score=12, total_positive=1, total_negative=0)),
    ],
    ids=["302-deprecated-redirect", "403", "404", "invalid-json", "score-off-scale"],
)
async def test_failed_reviews_keep_cached_scores_through_real_client(async_session, transport, reviews_response):
    """The outage behind this fix (a 302 for every app) and every other non-429
    failure must not overwrite a known game's scores with zeros."""
    transport.add("GET", APPDETAILS_PATH, httpx.Response(200, json=_appdetails()))
    transport.add("GET", REVIEWS_PATH, reviews_response)
    async with SteamClient(transport=transport) as client:
        service = GameService(async_session, client)
        await _seed_cached(service)
        before = utcnow()

        outcome = await service.refresh_game(APP_ID)

    assert outcome.status is FetchStatus.REFRESHED
    game = await service.repo.get_by_id(APP_ID)
    assert (game.review_score, game.total_positive, game.total_negative, game.total_reviews) == (8, 900, 100, 1000)
    assert game.genres == ["Action", "Indie"]
    assert game.last_refreshed_at >= before
    assert not steam_cooldown.active
    assert _paths(transport) == [APPDETAILS_PATH, REVIEWS_PATH]


async def test_deprecated_endpoint_is_never_requested(async_session, transport):
    """Only appdetails and GetAppReviews are reached for a game; /appreviews/
    is gone (RoutedTransport would raise on any unregistered path)."""
    transport.add("GET", APPDETAILS_PATH, httpx.Response(200, json=_appdetails()))
    transport.add(
        "GET", REVIEWS_PATH, httpx.Response(200, json=_summary(review_score=9, total_positive=95, total_negative=5))
    )
    async with SteamClient(transport=transport) as client:
        service = GameService(async_session, client)
        outcome = await service.refresh_game(APP_ID)

    assert outcome.status is FetchStatus.REFRESHED
    assert all("/appreviews" not in str(r.url) for r in transport.requests)
    [_details, reviews] = transport.requests
    assert reviews.url.host == "api.steampowered.com"


async def test_review_success_replaces_placeholder_zeros_through_real_client(async_session, transport):
    """A row that holds zeros from the outage gets Steam's summary and a fresh stamp."""
    transport.add("GET", APPDETAILS_PATH, httpx.Response(200, json=_appdetails()))
    transport.add(
        "GET",
        REVIEWS_PATH,
        httpx.Response(200, json=_summary(review_score=9, total_positive=950, total_negative=50, total_reviews=1000)),
    )
    async with SteamClient(transport=transport) as client:
        service = GameService(async_session, client)
        await _seed_cached(service, review_score=0, total_positive=0, total_negative=0, total_reviews=0)
        before = utcnow()

        outcome = await service.refresh_game(APP_ID)

    assert outcome.status is FetchStatus.REFRESHED
    game = outcome.game
    assert (game.review_score, game.total_positive, game.total_negative, game.total_reviews) == (9, 950, 50, 1000)
    assert game.last_refreshed_at >= before
    assert game.needs_refresh is False


async def test_new_row_with_302_reviews_is_created_unrefreshed(async_session, transport):
    """D4 through the real client: the deprecated-style 302 on a new game
    creates the row with zeros and last_refreshed_at NULL, reports FAILED,
    and starts no cool-down."""
    transport.add("GET", APPDETAILS_PATH, httpx.Response(200, json=_appdetails()))
    transport.add("GET", REVIEWS_PATH, httpx.Response(302, headers={"location": "https://store.steampowered.com/"}))
    async with SteamClient(transport=transport) as client:
        service = GameService(async_session, client)
        outcome = await service.refresh_game(APP_ID)

    assert outcome.status is FetchStatus.FAILED
    assert outcome.refreshed is False
    game = await service.repo.get_by_id(APP_ID)
    assert game is not None
    assert (game.review_score, game.total_reviews) == (0, 0)
    assert game.genres == ["Action", "Indie"]
    assert game.last_refreshed_at is None
    assert [g.id for g in await service.repo.get_stale_games()] == [APP_ID]
    assert not steam_cooldown.active
    assert len(transport.requests) == 2


async def test_existing_placeholder_with_failed_reviews_gets_retry_stamp_through_real_client(
    async_session, transport
):
    """An existing row with no cached reviews whose GetAppReviews call answers
    403 keeps its zeros, gets now - 7 d + REVIEW_RETRY_DELAY and FAILED."""
    transport.add("GET", APPDETAILS_PATH, httpx.Response(200, json=_appdetails()))
    transport.add("GET", REVIEWS_PATH, httpx.Response(403))
    async with SteamClient(transport=transport) as client:
        service = GameService(async_session, client)
        await _seed_cached(
            service, review_score=0, total_positive=0, total_negative=0, total_reviews=0, last_refreshed_at=None
        )
        before = utcnow()

        outcome = await service.refresh_game(APP_ID)
        after = utcnow()

    assert outcome.status is FetchStatus.FAILED
    game = await service.repo.get_by_id(APP_ID)
    offset = timedelta(days=STALE_AFTER_DAYS) - REVIEW_RETRY_DELAY
    assert before - offset <= game.last_refreshed_at <= after - offset
    assert (game.review_score, game.total_reviews) == (0, 0)
    assert await service.repo.get_stale_games() == []
    assert not steam_cooldown.active


async def test_no_summary_on_new_row_is_no_reviews_through_real_client(async_session, transport):
    """{"response": {}} (unknown app, or no reviews) is data: zeros, stamped, REFRESHED."""
    transport.add("GET", APPDETAILS_PATH, httpx.Response(200, json=_appdetails()))
    transport.add("GET", REVIEWS_PATH, httpx.Response(200, json={"response": {}}))
    async with SteamClient(transport=transport) as client:
        service = GameService(async_session, client)
        before = utcnow()
        outcome = await service.refresh_game(APP_ID)

    assert outcome.status is FetchStatus.REFRESHED
    assert (outcome.game.review_score, outcome.game.total_reviews) == (0, 0)
    assert outcome.game.last_refreshed_at >= before
    assert not steam_cooldown.active


async def test_reviews_429_trips_cooldown_and_blocks_further_steam_requests(async_session, transport):
    """A 429 from GetAppReviews keeps the cached scores and the old refresh
    time, starts the shared cool-down, and no Steam request at all is sent
    while it runs (refresh_game, refresh_stale_games, read-through lookup)."""
    transport.add("GET", APPDETAILS_PATH, httpx.Response(200, json=_appdetails()))
    transport.add("GET", REVIEWS_PATH, httpx.Response(429))
    async with SteamClient(transport=transport) as client:
        service = GameService(async_session, client)
        old_stamp = utcnow() - timedelta(days=30)
        await _seed_cached(service, last_refreshed_at=old_stamp)

        outcome = await service.refresh_game(APP_ID)

        assert outcome.status is FetchStatus.RATE_LIMITED
        assert steam_cooldown.active
        assert len(transport.requests) == 2
        game = await service.repo.get_by_id(APP_ID)
        assert (game.review_score, game.total_reviews) == (8, 1000)
        assert game.last_refreshed_at == old_stamp

        assert (await service.refresh_game(APP_ID)).status is FetchStatus.RATE_LIMITED
        assert await service.refresh_stale_games(limit=10) == 0
        assert await service.get_or_fetch_game(APP_ID + 1) is None

    assert len(transport.requests) == 2


async def test_reviews_5xx_retries_are_bounded_and_keep_cached_scores(async_session, transport, no_sleep):
    """A 500 that outlives _request's retries is a failure: four GetAppReviews
    attempts (backoff 1, 2, 4 s), cached scores kept, no cool-down."""
    transport.add("GET", APPDETAILS_PATH, httpx.Response(200, json=_appdetails()))
    transport.add("GET", REVIEWS_PATH, httpx.Response(500))
    async with SteamClient(transport=transport) as client:
        service = GameService(async_session, client)
        await _seed_cached(service)

        outcome = await service.refresh_game(APP_ID)

    assert outcome.status is FetchStatus.REFRESHED
    assert (outcome.game.review_score, outcome.game.total_reviews) == (8, 1000)
    assert _paths(transport) == [APPDETAILS_PATH] + [REVIEWS_PATH] * 4
    assert [c.args[0] for c in no_sleep.call_args_list] == [1, 2, 4]
    assert not steam_cooldown.active


@pytest.mark.parametrize("app_type", ["dlc", "bundle"])
async def test_no_reviews_request_for_dlc_or_bundle(async_session, transport, app_type):
    """Only appdetails is requested for a DLC or a bundle; the row is stamped."""
    transport.add("GET", APPDETAILS_PATH, httpx.Response(200, json=_appdetails(app_type)))
    async with SteamClient(transport=transport) as client:
        service = GameService(async_session, client)
        outcome = await service.refresh_game(APP_ID)

    assert outcome.status is FetchStatus.REFRESHED
    assert outcome.game.last_refreshed_at is not None
    assert _paths(transport) == [APPDETAILS_PATH]
