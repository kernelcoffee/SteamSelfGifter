"""POST /api/v1/games/{app_id}/refresh when GetAppReviews fails.

The game service gets a real SteamClient over an httpx.MockTransport, so the
response is what the router builds from the real client's exceptions.
"""

from collections.abc import AsyncGenerator
from datetime import timedelta

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.dependencies import DatabaseDep, get_game_service
from api.main import app
from core.time import utcnow
from models.game import Game
from repositories.game import STALE_AFTER_DAYS
from services.game_service import REVIEW_RETRY_DELAY, GameService

APP_ID = 367520
APPDETAILS = {
    str(APP_ID): {
        "success": True,
        "data": {
            "type": "game",
            "name": "Hollow Knight",
            "steam_appid": APP_ID,
            "genres": [{"id": "1", "description": "Action"}],
            "categories": [{"id": 2, "description": "Single-player"}],
            "release_date": {"coming_soon": False, "date": "Feb 24, 2017"},
        },
    }
}


@pytest.fixture
async def steam_requests(test_client: AsyncClient) -> AsyncGenerator[list[httpx.Request]]:
    """Route the endpoint's SteamClient to a transport whose GetAppReviews answers 403."""
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if request.url.path == "/api/appdetails":
            return httpx.Response(200, json=APPDETAILS)
        if request.url.path == "/IUserReviewsService/GetAppReviews/v1/":
            return httpx.Response(403)
        raise AssertionError(f"Unexpected request: {request.url}")

    clients = []

    async def override(db: DatabaseDep) -> GameService:
        from utils.steam_client import SteamClient

        client = SteamClient(transport=httpx.MockTransport(handler))
        await client.start()
        clients.append(client)
        return GameService(db, client)

    app.dependency_overrides[get_game_service] = override
    yield sent
    for client in clients:
        await client.close()


async def _seed(async_engine, game: Game) -> None:
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        session.add(game)
        await session.commit()


async def _load(async_engine) -> Game:
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        return await session.get(Game, APP_ID)


@pytest.mark.asyncio
async def test_refresh_without_cached_reviews_reports_not_refreshed(
    test_client: AsyncClient, async_engine, steam_requests
):
    """No cached reviews and a failed GetAppReviews: refreshed false, the
    documented message, last_refreshed_at null in the body; the appdetails
    fields are saved and the row carries the retry stamp, not a fresh one."""
    await _seed(async_engine, Game(id=APP_ID, name="Placeholder", type="game", last_refreshed_at=None))
    before = utcnow()

    response = await test_client.post(f"/api/v1/games/{APP_ID}/refresh")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["refreshed"] is False
    assert data["message"] == "Steam request failed, cached data kept"
    assert data["last_refreshed_at"] is None
    game = await _load(async_engine)
    assert game.name == "Hollow Knight"
    assert game.genres == ["Action"]
    assert (game.review_score, game.total_reviews) == (0, 0)
    offset = timedelta(days=STALE_AFTER_DAYS) - REVIEW_RETRY_DELAY
    assert before - offset <= game.last_refreshed_at <= utcnow() - offset
    assert [r.url.path for r in steam_requests] == ["/api/appdetails", "/IUserReviewsService/GetAppReviews/v1/"]


@pytest.mark.asyncio
async def test_refresh_with_cached_reviews_keeps_them_and_reports_refreshed(
    test_client: AsyncClient, async_engine, steam_requests
):
    """Cached reviews survive a failed GetAppReviews: refreshed true with the
    new refresh time, and the stored scores are unchanged."""
    await _seed(async_engine, Game(
        id=APP_ID, name="Cached", type="game", review_score=8, total_positive=900,
        total_negative=100, total_reviews=1000, last_refreshed_at=utcnow() - timedelta(days=30),
    ))

    response = await test_client.post(f"/api/v1/games/{APP_ID}/refresh")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["refreshed"] is True
    assert data["last_refreshed_at"] is not None
    game = await _load(async_engine)
    assert (game.review_score, game.total_positive, game.total_negative, game.total_reviews) == (8, 900, 100, 1000)
    assert game.last_refreshed_at > utcnow() - timedelta(minutes=1)


@pytest.mark.asyncio
async def test_refresh_response_serializes_last_refreshed_at_with_z_suffix(
    test_client: AsyncClient, async_engine, steam_requests
):
    """Convention: every datetime in an API response is UTC with a 'Z' suffix."""
    await _seed(async_engine, Game(
        id=APP_ID, name="Cached", type="game", review_score=8, total_positive=900,
        total_negative=100, total_reviews=1000, last_refreshed_at=utcnow() - timedelta(days=30),
    ))

    response = await test_client.post(f"/api/v1/games/{APP_ID}/refresh")

    assert response.status_code == 200
    assert response.json()["data"]["last_refreshed_at"].endswith("Z")
