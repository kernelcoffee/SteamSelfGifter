"""End-to-end tests for the games API genre listing."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.game import Game


async def _seed_games(async_engine, games: list[Game]) -> None:
    """Insert games straight into the test database the client uses."""
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        session.add_all(games)
        await session.commit()


@pytest.mark.asyncio
async def test_get_game_genres_counts_and_order(test_client: AsyncClient, async_engine):
    """Distinct genres with game counts, count desc then name asc; NULL and
    [] rows contribute nothing; any game type counts."""
    await _seed_games(async_engine, [
        Game(id=1, name="A", type="game", genres=["Action", "Indie"]),
        Game(id=2, name="B", type="dlc", genres=["RPG", "Action"]),
        Game(id=3, name="C", type="game", genres=None),
        Game(id=4, name="D", type="game", genres=[]),
    ])

    response = await test_client.get("/api/v1/games/genres")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {
        "genres": [
            {"name": "Action", "count": 2},
            {"name": "Indie", "count": 1},
            {"name": "RPG", "count": 1},
        ]
    }


@pytest.mark.asyncio
async def test_get_game_genres_empty_cache(test_client: AsyncClient):
    """An empty cache answers 200 with an empty list, and the path is not
    shadowed by /games/{app_id} (which would 422 on the int parser)."""
    response = await test_client.get("/api/v1/games/genres")

    assert response.status_code == 200
    assert response.json()["data"] == {"genres": []}


@pytest.mark.asyncio
async def test_get_game_includes_genres_and_categories(test_client: AsyncClient, async_engine):
    """GameResponse exposes genres/categories; unfetched stays null."""
    await _seed_games(async_engine, [
        Game(id=10, name="Fetched", type="game", genres=["Action"], categories=["Single-player"]),
    ])

    response = await test_client.get("/api/v1/games/")

    assert response.status_code == 200
    [game] = response.json()["data"]["games"]
    assert game["genres"] == ["Action"]
    assert game["categories"] == ["Single-player"]


@pytest.mark.asyncio
async def test_get_uncached_game_during_steam_cooldown_is_429(test_client: AsyncClient):
    """While the Steam cool-down is active, an uncached app id answers 429
    STEAM_003 with the retry time instead of 404 'not found'."""
    from services.game_service import steam_cooldown

    steam_cooldown.trip()
    response = await test_client.get("/api/v1/games/12345")

    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "STEAM_003"
    assert body["error"]["details"]["app_id"] == 12345
    assert 0 < body["error"]["details"]["retry_after_seconds"] <= 180


@pytest.mark.asyncio
async def test_game_response_unfetched_genres_are_null_and_empty_stays_empty(
    test_client: AsyncClient, async_engine
):
    """genres/categories NULL ("not fetched yet") serialize as null, [] as [],
    on both the list and the single-game endpoint (a fresh cached row, so no
    Steam call is made)."""
    from core.time import utcnow

    await _seed_games(async_engine, [
        Game(id=20, name="Legacy", type="game", last_refreshed_at=utcnow()),
        Game(id=21, name="None", type="game", genres=[], categories=[],
             last_refreshed_at=utcnow()),
    ])

    response = await test_client.get("/api/v1/games/")
    assert response.status_code == 200
    by_id = {g["id"]: g for g in response.json()["data"]["games"]}
    assert by_id[20]["genres"] is None and by_id[20]["categories"] is None
    assert by_id[21]["genres"] == [] and by_id[21]["categories"] == []

    response = await test_client.get("/api/v1/games/21")
    assert response.status_code == 200
    assert response.json()["data"]["genres"] == []
