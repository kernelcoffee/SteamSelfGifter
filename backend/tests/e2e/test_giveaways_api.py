"""End-to-end tests for the joined game_genres field on giveaway endpoints."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.game import Game
from models.giveaway import Giveaway


async def _seed(async_engine, rows: list[object]) -> None:
    """Insert rows straight into the test database the client uses."""
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        session.add_all(rows)
        await session.commit()


def _game(app_id: int, genres: list[str] | None) -> Game:
    """A cached game refreshed just now, so enrichment never calls Steam."""
    return Game(
        id=app_id,
        name=f"Game {app_id}",
        type="game",
        genres=genres,
        categories=[],
        last_refreshed_at=datetime.now(UTC),
    )


def _giveaway(code: str, game_id: int | None, *, is_entered: bool = False) -> Giveaway:
    now = datetime.now(UTC)
    return Giveaway(
        code=code,
        url=f"https://www.steamgifts.com/giveaway/{code}/",
        game_id=game_id,
        game_name=f"Giveaway {code}",
        price=10,
        end_time=now + timedelta(days=1),
        is_entered=is_entered,
        entered_at=now if is_entered else None,
    )


@pytest.mark.asyncio
async def test_get_giveaway_by_code_includes_game_genres(test_client: AsyncClient, async_engine):
    """GET /giveaways/{code} carries the cached game's genres; no game_id
    gives null."""
    await _seed(async_engine, [_game(620, ["Action"])])
    await _seed(async_engine, [_giveaway("ABCDE", 620), _giveaway("NOGME", None)])

    response = await test_client.get("/api/v1/giveaways/ABCDE")
    assert response.status_code == 200
    assert response.json()["data"]["game_genres"] == ["Action"]

    response = await test_client.get("/api/v1/giveaways/NOGME")
    assert response.status_code == 200
    assert response.json()["data"]["game_genres"] is None


@pytest.mark.asyncio
async def test_get_entered_giveaways_route(test_client: AsyncClient, async_engine):
    """GET /giveaways/entered is a list of entered giveaways with
    game_genres, not a lookup of the giveaway code 'entered'."""
    await _seed(async_engine, [_game(620, ["Action", "Indie"])])
    await _seed(async_engine, [
        _giveaway("ENTR1", 620, is_entered=True),
        _giveaway("OPEN1", 620),
    ])

    response = await test_client.get("/api/v1/giveaways/entered")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["count"] == 1
    assert [g["code"] for g in data["giveaways"]] == ["ENTR1"]
    assert data["giveaways"][0]["game_genres"] == ["Action", "Indie"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/api/v1/giveaways",
    "/api/v1/giveaways/active",
    "/api/v1/giveaways/wishlist",
    "/api/v1/giveaways/dlc",
    "/api/v1/giveaways/won",
])
async def test_enriched_list_endpoints_carry_game_genres(
    test_client: AsyncClient, async_engine, path
):
    """Every enriched list endpoint exposes game_genres: the cached list
    (including []), and null for genres not fetched yet or no game_id."""
    await _seed(async_engine, [
        _game(620, ["Action", "Indie"]),
        _game(621, []),
        _game(622, None),
    ])
    rows = []
    for code, game_id in [("GACTN", 620), ("GEMPT", 621), ("GNULL", 622), ("GNOID", None)]:
        gw = _giveaway(code, game_id)
        gw.is_wishlist = True
        gw.is_dlc = True
        gw.is_won = True
        gw.won_at = datetime.now(UTC)
        rows.append(gw)
    await _seed(async_engine, rows)

    response = await test_client.get(path)

    assert response.status_code == 200
    by_code = {g["code"]: g for g in response.json()["data"]["giveaways"]}
    assert set(by_code) == {"GACTN", "GEMPT", "GNULL", "GNOID"}
    assert by_code["GACTN"]["game_genres"] == ["Action", "Indie"]
    assert by_code["GEMPT"]["game_genres"] == []
    assert by_code["GNULL"]["game_genres"] is None
    assert by_code["GNOID"]["game_genres"] is None
    for giveaway in by_code.values():
        assert "game_genres" in giveaway
