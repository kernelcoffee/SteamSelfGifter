"""Unit tests for GameService."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.time import utcnow
from models.base import Base
from services.game_service import FetchStatus, GameService, SteamCooldown, steam_cooldown
from utils.steam_client import SteamAPIError, SteamAPIRateLimitError, SteamClient

# appdetails `data` fixtures (trimmed to the fields the save path reads).
STEAM_GAME_WITH_GENRES = {
    "type": "game",
    "name": "Hollow Knight",
    "steam_appid": 367520,
    "is_free": False,
    "header_image": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/367520/header.jpg",
    "price_overview": {"currency": "USD", "initial": 1499, "final": 1499, "discount_percent": 0},
    "categories": [
        {"id": 2, "description": "Single-player"},
        {"id": 22, "description": "Steam Achievements"},
        {"id": 28, "description": "Full controller support"},
        {"id": 29, "description": "Steam Trading Cards"},
        {"id": 23, "description": "Steam Cloud"},
    ],
    "genres": [
        {"id": "1", "description": "Action"},
        {"id": "25", "description": "Adventure"},
        {"id": "23", "description": "Indie"},
    ],
    "release_date": {"coming_soon": False, "date": "Feb 24, 2017"},
}
STEAM_DLC = {
    "type": "dlc",
    "name": "Cities: Skylines - After Dark",
    "steam_appid": 369150,
    "is_free": False,
    "fullgame": {"appid": "255710", "name": "Cities: Skylines"},
    "categories": [
        {"id": 2, "description": "Single-player"},
        {"id": 21, "description": "Downloadable Content"},
        {"id": 22, "description": "Steam Achievements"},
    ],
    "genres": [
        {"id": "28", "description": "Simulation"},
        {"id": "2", "description": "Strategy"},
    ],
    "release_date": {"coming_soon": False, "date": "24 Sep, 2015"},
}
STEAM_APP_NO_GENRES = {
    "type": "game",
    "name": "Obscure Legacy Title",
    "steam_appid": 12345,
    "is_free": True,
    "release_date": {"coming_soon": True, "date": "Coming soon"},
}


# Test database setup
@pytest.fixture
async def test_db():
    """Create in-memory test database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    yield async_session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def mock_steam_client():
    """Create mock Steam client with async methods."""
    client = MagicMock(spec=SteamClient)
    # Set up async methods with default returns
    client.get_app_details = AsyncMock(return_value=None)
    # get_app_reviews must return values that satisfy NOT NULL constraints
    client.get_app_reviews = AsyncMock(return_value={
        "review_score": 0,
        "total_positive": 0,
        "total_negative": 0,
        "total_reviews": 0,
    })
    return client


@pytest.mark.asyncio
async def test_game_service_init(test_db, mock_steam_client):
    """Test GameService initialization."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        assert service.session == session
        assert service.steam_client == mock_steam_client
        assert service.repo is not None


@pytest.mark.asyncio
async def test_get_or_fetch_game_from_cache(test_db, mock_steam_client):
    """Test getting game from cache when fresh."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        # Create fresh game in cache
        await service.repo.create(
            id=730,
            name="CS:GO",
            type="game",
            last_refreshed_at=utcnow(),
            genres=["Action"],
        )
        await session.commit()

        # Should return cached version without calling Steam API
        result = await service.get_or_fetch_game(730)

        assert result is not None
        assert result.id == 730
        assert result.name == "CS:GO"
        # Steam API should not have been called
        mock_steam_client.get_app_details.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_fetch_game_fetches_when_stale(test_db, mock_steam_client):
    """Test fetching game from API when cache is stale."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        # Create stale game in cache (include review fields which are NOT NULL)
        old_date = utcnow() - timedelta(days=35)
        await service.repo.create(
            id=730,
            name="Old CS:GO",
            type="game",
            last_refreshed_at=old_date,
            review_score=0,
            total_positive=0,
            total_negative=0,
            total_reviews=0,
        )
        await session.commit()

        # Mock Steam API response
        mock_steam_client.get_app_details = AsyncMock(
            return_value={
                "name": "Counter-Strike: Global Offensive",
                "type": "game",
                "release_date": {"coming_soon": False, "date": "Aug 21, 2012"},
            }
        )

        # Should fetch from API and update cache
        result = await service.get_or_fetch_game(730)

        assert result is not None
        assert result.id == 730
        assert result.name == "Counter-Strike: Global Offensive"
        mock_steam_client.get_app_details.assert_called_once_with(730)


@pytest.mark.asyncio
async def test_get_or_fetch_game_creates_new(test_db, mock_steam_client):
    """Test fetching game from API when not in cache."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        # Mock Steam API response
        mock_steam_client.get_app_details = AsyncMock(
            return_value={
                "name": "Portal 2",
                "type": "game",
                "release_date": {"coming_soon": False, "date": "Apr 19, 2011"},
            }
        )

        # Should fetch from API and create new entry
        result = await service.get_or_fetch_game(620)

        assert result is not None
        assert result.id == 620
        assert result.name == "Portal 2"
        mock_steam_client.get_app_details.assert_called_once_with(620)


@pytest.mark.asyncio
async def test_get_or_fetch_game_not_found(test_db, mock_steam_client):
    """Test handling when game not found on Steam."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        # Mock Steam API returning None (not found)
        mock_steam_client.get_app_details = AsyncMock(return_value=None)

        result = await service.get_or_fetch_game(999999)

        assert result is None
        mock_steam_client.get_app_details.assert_called_once_with(999999)


@pytest.mark.asyncio
async def test_get_or_fetch_game_force_refresh(test_db, mock_steam_client):
    """Test force refreshing even when cache is fresh."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        # Create fresh game in cache (include review fields which are NOT NULL)
        await service.repo.create(
            id=730,
            name="Old Name",
            type="game",
            last_refreshed_at=utcnow(),
            review_score=0,
            total_positive=0,
            total_negative=0,
            total_reviews=0,
        )
        await session.commit()

        # Mock Steam API response
        mock_steam_client.get_app_details = AsyncMock(
            return_value={"name": "New Name", "type": "game", "release_date": {}}
        )

        # Force refresh should call API even though cache is fresh
        result = await service.get_or_fetch_game(730, force_refresh=True)

        assert result.name == "New Name"
        mock_steam_client.get_app_details.assert_called_once_with(730)


@pytest.mark.asyncio
async def test_get_or_fetch_game_api_error_returns_cache(test_db, mock_steam_client):
    """Test returning cached data when API errors."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        # Create stale game in cache
        old_date = utcnow() - timedelta(days=35)
        await service.repo.create(
            id=730,
            name="CS:GO",
            type="game",
            last_refreshed_at=old_date,
        )
        await session.commit()

        # Mock Steam API error
        mock_steam_client.get_app_details = AsyncMock(
            side_effect=SteamAPIError("API error")
        )

        # Should return cached data despite error
        result = await service.get_or_fetch_game(730)

        assert result is not None
        assert result.id == 730
        assert result.name == "CS:GO"


@pytest.mark.asyncio
async def test_save_game_from_steam_data_new_game(test_db, mock_steam_client):
    """Test saving new game from Steam data."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        steam_data = {
            "name": "Test Game",
            "type": "game",
            "release_date": {"coming_soon": False, "date": "Jan 1, 2020"},
        }

        game = await service._save_game_from_steam_data(123, steam_data)

        assert game.id == 123
        assert game.name == "Test Game"
        assert game.type == "game"
        assert game.last_refreshed_at is not None


@pytest.mark.asyncio
async def test_save_game_from_steam_data_updates_existing(test_db, mock_steam_client):
    """Test updating existing game from Steam data."""
    import asyncio

    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        # Create existing game with old timestamp
        old_timestamp = utcnow() - timedelta(days=30)
        await service.repo.create(
            id=123,
            name="Old Name",
            type="game",
            last_refreshed_at=old_timestamp,
        )
        await session.commit()

        # Small delay to ensure different timestamp
        await asyncio.sleep(0.01)

        steam_data = {
            "name": "New Name",
            "type": "game",
            "release_date": {"coming_soon": False, "date": "Jan 1, 2020"},
        }

        game = await service._save_game_from_steam_data(123, steam_data)

        assert game.id == 123
        assert game.name == "New Name"
        # Should have updated last_refreshed_at
        assert game.last_refreshed_at > old_timestamp


@pytest.mark.asyncio
async def test_save_game_from_steam_data_dlc(test_db, mock_steam_client):
    """Test saving DLC with parent game reference."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        steam_data = {
            "name": "Test DLC",
            "type": "dlc",
            "release_date": {},
            "fullgame": {"appid": "999"},
        }

        game = await service._save_game_from_steam_data(456, steam_data)

        assert game.id == 456
        assert game.type == "dlc"
        assert game.game_id == 999  # Parent game ID


@pytest.mark.asyncio
async def test_refresh_stale_games(test_db, mock_steam_client):
    """Test refreshing multiple stale games."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        # Create stale games (include review fields which are NOT NULL)
        old_date = utcnow() - timedelta(days=35)
        for i in range(3):
            await service.repo.create(
                id=100 + i,
                name=f"Game {i}",
                type="game",
                last_refreshed_at=old_date,
                review_score=0,
                total_positive=0,
                total_negative=0,
                total_reviews=0,
            )
        await session.commit()

        # Mock Steam API responses
        mock_steam_client.get_app_details = AsyncMock(
            return_value={"name": "Updated", "type": "game", "release_date": {}}
        )

        count = await service.refresh_stale_games(limit=2)

        assert count == 2
        # Should have called API 2 times (limit=2)
        assert mock_steam_client.get_app_details.call_count == 2


@pytest.mark.asyncio
async def test_refresh_stale_games_handles_errors(test_db, mock_steam_client):
    """Test refresh continues on errors."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        # Create stale games (include review fields which are NOT NULL)
        old_date = utcnow() - timedelta(days=35)
        for i in range(3):
            await service.repo.create(
                id=100 + i,
                name=f"Game {i}",
                type="game",
                last_refreshed_at=old_date,
                review_score=0,
                total_positive=0,
                total_negative=0,
                total_reviews=0,
            )
        await session.commit()

        # Mock API: first call errors, second succeeds, third errors
        mock_steam_client.get_app_details = AsyncMock(
            side_effect=[
                SteamAPIError("Error"),
                {"name": "Success", "type": "game", "release_date": {}},
                SteamAPIError("Error"),
            ]
        )

        count = await service.refresh_stale_games(limit=3)

        # Only 1 should succeed
        assert count == 1


@pytest.mark.asyncio
async def test_search_games(test_db, mock_steam_client):
    """Test searching games by name."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        # Create games
        await service.repo.create(id=1, name="Portal", type="game")
        await service.repo.create(id=2, name="Portal 2", type="game")
        await service.repo.create(id=3, name="Half-Life", type="game")
        await session.commit()

        results = await service.search_games("portal")

        assert len(results) == 2
        assert all("portal" in game.name.lower() for game in results)


@pytest.mark.asyncio
async def test_get_highly_rated_games(test_db, mock_steam_client):
    """Test getting highly-rated games."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        # Create games with different ratings
        await service.repo.create(
            id=1, name="Great Game", type="game", review_score=9, total_reviews=5000
        )
        await service.repo.create(
            id=2, name="Good Game", type="game", review_score=8, total_reviews=2000
        )
        await service.repo.create(
            id=3, name="Bad Game", type="game", review_score=5, total_reviews=100
        )
        await session.commit()

        results = await service.get_highly_rated_games(min_score=8, min_reviews=1000)

        assert len(results) == 2
        assert all(game.review_score >= 8 for game in results)


@pytest.mark.asyncio
async def test_get_games_by_type(test_db, mock_steam_client):
    """Test getting games by type."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        # Create different types
        await service.repo.create(id=1, name="Game 1", type="game")
        await service.repo.create(id=2, name="DLC 1", type="dlc")
        await service.repo.create(id=3, name="Game 2", type="game")
        await session.commit()

        games = await service.get_games_by_type("game")
        dlcs = await service.get_games_by_type("dlc")

        assert len(games) == 2
        assert len(dlcs) == 1


@pytest.mark.asyncio
async def test_get_game_cache_stats(test_db, mock_steam_client):
    """Test getting cache statistics."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        # Create fresh and stale games
        fresh_date = utcnow()
        stale_date = utcnow() - timedelta(days=35)

        await service.repo.create(
            id=1, name="Fresh Game", type="game", last_refreshed_at=fresh_date, genres=["Action"]
        )
        await service.repo.create(
            id=2, name="Stale Game", type="game", last_refreshed_at=stale_date, genres=["Action"]
        )
        await service.repo.create(
            id=3, name="DLC", type="dlc", last_refreshed_at=fresh_date, genres=[]
        )
        await session.commit()

        stats = await service.get_game_cache_stats()

        assert stats["total"] == 3
        assert stats["by_type"]["game"] == 2
        assert stats["by_type"]["dlc"] == 1
        assert stats["stale_count"] == 1


@pytest.mark.asyncio
async def test_bulk_cache_games(test_db, mock_steam_client):
    """Test bulk caching multiple games."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        # Mock Steam API
        mock_steam_client.get_app_details = AsyncMock(
            return_value={"name": "Test", "type": "game", "release_date": {}}
        )

        app_ids = [730, 440, 570]
        count = await service.bulk_cache_games(app_ids)

        assert count == 3
        assert mock_steam_client.get_app_details.call_count == 3


@pytest.mark.asyncio
async def test_bulk_cache_games_skips_fresh(test_db, mock_steam_client):
    """Test bulk cache skips fresh games."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        # Create fresh game
        await service.repo.create(
            id=730, name="CS:GO", type="game", last_refreshed_at=utcnow(), genres=["Action"]
        )
        await session.commit()

        # Mock Steam API
        mock_steam_client.get_app_details = AsyncMock(
            return_value={"name": "Test", "type": "game", "release_date": {}}
        )

        app_ids = [730, 440]
        count = await service.bulk_cache_games(app_ids)

        # Should only cache 440 (730 is fresh)
        assert count == 1
        mock_steam_client.get_app_details.assert_called_once_with(440)


# ---------------------------------------------------------------------------
# Genres and categories
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_game_extracts_genres_and_categories(test_db, mock_steam_client):
    """Description strings are stored in Steam's order; ids are dropped."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        game = await service._save_game_from_steam_data(367520, STEAM_GAME_WITH_GENRES)
        await session.commit()
        stored = await service.repo.get_by_id(367520)

        assert game.genres == ["Action", "Adventure", "Indie"]
        assert stored.categories == [
            "Single-player", "Steam Achievements", "Full controller support",
            "Steam Trading Cards", "Steam Cloud",
        ]
        assert stored.needs_refresh is False


@pytest.mark.asyncio
async def test_save_game_without_genre_keys_stores_empty_lists(test_db, mock_steam_client):
    """Steam omits the keys when there are none: store [] (fetched, none), never None."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        game = await service._save_game_from_steam_data(12345, STEAM_APP_NO_GENRES)

        assert game.genres == []
        assert game.categories == []
        assert game.release_date is None
        assert game.needs_refresh is False


@pytest.mark.asyncio
async def test_save_game_skips_malformed_genre_items(test_db, mock_steam_client):
    """Items without a string, non-blank description (or not dicts) are skipped;
    a non-list value yields []."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        steam_data = {
            **STEAM_GAME_WITH_GENRES,
            "genres": [
                {"id": "1", "description": "Action"}, {"id": "23"}, {"id": "3", "description": 3},
                {"id": "4", "description": "  "}, "RPG", {"id": "28", "description": "Simulation"},
            ],
            "categories": {"id": 2, "description": "Single-player"},
        }

        game = await service._save_game_from_steam_data(367520, steam_data)

        assert game.genres == ["Action", "Simulation"]
        assert game.categories == []


@pytest.mark.asyncio
async def test_save_game_update_backfills_genres(test_db, mock_steam_client):
    """An existing row with genres NULL gets the lists on refresh and stops being stale."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        old = utcnow() - timedelta(hours=1)
        await service.repo.create(id=367520, name="Old", type="game", last_refreshed_at=old)
        await session.commit()
        assert (await service.repo.get_by_id(367520)).needs_refresh is True

        game = await service._save_game_from_steam_data(367520, STEAM_GAME_WITH_GENRES)
        await session.commit()

        assert game.genres == ["Action", "Adventure", "Indie"]
        assert game.categories[0] == "Single-player"
        assert game.last_refreshed_at > old
        assert game.needs_refresh is False
        assert await service.repo.get_stale_games() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("game_type", ["dlc", "bundle"])
async def test_save_game_stores_genres_for_every_type(test_db, mock_steam_client, game_type):
    """DLC and bundle payloads get genres/categories too (no reviews call)."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)

        game = await service._save_game_from_steam_data(
            369150, {**STEAM_DLC, "type": game_type}
        )

        assert game.genres == ["Simulation", "Strategy"]
        assert game.categories == ["Single-player", "Downloadable Content", "Steam Achievements"]
        mock_steam_client.get_app_reviews.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_stale_games_backfills_genres_refreshed_today(test_db, mock_steam_client):
    """A row refreshed today but with genres NULL is picked up and backfilled;
    with limit=1 and two such rows, one Steam request per cycle."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        now = utcnow()
        await service.repo.create(id=1, name="A", type="dlc", last_refreshed_at=now - timedelta(minutes=5))
        await service.repo.create(id=2, name="B", type="dlc", last_refreshed_at=now)
        await session.commit()
        mock_steam_client.get_app_details = AsyncMock(return_value=STEAM_DLC)

        assert await service.refresh_stale_games(limit=1) == 1
        assert mock_steam_client.get_app_details.call_count == 1
        mock_steam_client.get_app_details.assert_called_with(1)
        assert (await service.repo.get_by_id(1)).genres == ["Simulation", "Strategy"]
        assert (await service.repo.get_by_id(2)).genres is None

        assert await service.refresh_stale_games(limit=1) == 1
        mock_steam_client.get_app_details.assert_called_with(2)
        assert (await service.repo.get_by_id(2)).genres == ["Simulation", "Strategy"]
        assert await service.repo.get_stale_games() == []


@pytest.mark.asyncio
async def test_refresh_stale_games_unavailable_app_does_not_starve_queue(test_db, mock_steam_client):
    """An app Steam no longer serves is marked checked (genres [] and a fresh
    last_refreshed_at), so it leaves the stale queue and the next cycle
    reaches the good row."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        now = utcnow()
        await service.repo.create(id=1, name="Delisted", type="dlc", last_refreshed_at=now - timedelta(days=30))
        await service.repo.create(id=2, name="Good", type="dlc", last_refreshed_at=now - timedelta(days=1))
        await session.commit()

        async def details(app_id):
            return None if app_id == 1 else STEAM_DLC

        mock_steam_client.get_app_details = AsyncMock(side_effect=details)

        assert await service.refresh_stale_games(limit=1) == 0
        delisted = await service.repo.get_by_id(1)
        assert delisted.genres == []
        assert delisted.categories == []
        assert delisted.needs_refresh is False

        assert await service.refresh_stale_games(limit=1) == 1
        assert (await service.repo.get_by_id(2)).genres == ["Simulation", "Strategy"]
        assert [c.args[0] for c in mock_steam_client.get_app_details.call_args_list] == [1, 2]


@pytest.mark.asyncio
async def test_refresh_stale_games_stops_on_rate_limit_and_keeps_saved(test_db, mock_steam_client):
    """The first rate-limit error ends the batch; rows saved before it are committed."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        old = utcnow() - timedelta(days=30)
        for i in range(3):
            await service.repo.create(id=i + 1, name=f"G{i}", type="dlc", last_refreshed_at=old + timedelta(minutes=i))
        await session.commit()
        mock_steam_client.get_app_details = AsyncMock(
            side_effect=[STEAM_DLC, SteamAPIRateLimitError("429"), STEAM_DLC]
        )

        assert await service.refresh_stale_games(limit=3) == 1
        assert mock_steam_client.get_app_details.call_count == 2
        await session.rollback()
        assert (await service.repo.get_by_id(1)).genres == ["Simulation", "Strategy"]
        assert (await service.repo.get_by_id(3)).genres is None


@pytest.mark.asyncio
async def test_get_or_fetch_game_unavailable_marks_cached_row_checked(test_db, mock_steam_client):
    """A cached legacy row (genres NULL, stale by age) that Steam no longer
    serves is returned as cached (its thumbnail and reviews are kept) and
    marked checked, so the next call is a cache hit instead of another
    request."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        await service.repo.create(
            id=55, name="Gone", type="game", review_score=8, total_reviews=900,
            header_image="https://example.invalid/55.jpg",
            last_refreshed_at=utcnow() - timedelta(days=10),
        )
        await session.commit()
        mock_steam_client.get_app_details = AsyncMock(return_value=None)

        first = await service.get_or_fetch_game(55)
        again = await service.get_or_fetch_game(55)

        assert first is not None
        assert first.review_score == 8
        assert first.header_image == "https://example.invalid/55.jpg"
        assert again is not None and again.genres == []
        mock_steam_client.get_app_details.assert_called_once_with(55)


@pytest.mark.asyncio
async def test_get_or_fetch_game_unavailable_uncached_returns_none(test_db, mock_steam_client):
    """An app that is neither cached nor served by Steam is still "not found"."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        mock_steam_client.get_app_details = AsyncMock(return_value=None)

        assert await service.get_or_fetch_game(404) is None
        assert await service.repo.get_by_id(404) is None


@pytest.mark.asyncio
async def test_rate_limit_starts_cooldown_serving_cache(test_db, mock_steam_client):
    """After one 429 every later lookup, in this or another GameService,
    serves the cache (stale or genres NULL) without calling Steam."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        for app_id in (1, 2, 3):
            await service.repo.create(
                id=app_id, name=f"G{app_id}", type="game",
                last_refreshed_at=utcnow() - timedelta(days=30),
            )
        await session.commit()
        mock_steam_client.get_app_details = AsyncMock(side_effect=SteamAPIRateLimitError("429"))

        results = [await service.get_or_fetch_game(app_id) for app_id in (1, 2)]
        other = GameService(session, mock_steam_client)
        results.append(await other.get_or_fetch_game(3))
        uncached = await other.get_or_fetch_game(99)

        assert [r.id for r in results] == [1, 2, 3]
        assert uncached is None
        assert steam_cooldown.active
        mock_steam_client.get_app_details.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_cooldown_skips_refresh_stale_games_until_it_expires(test_db, mock_steam_client):
    """refresh_stale_games sends nothing during the cool-down and resumes after it."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        await service.repo.create(id=1, name="G", type="dlc", last_refreshed_at=utcnow())
        await session.commit()
        mock_steam_client.get_app_details = AsyncMock(side_effect=[SteamAPIRateLimitError("429"), STEAM_DLC])

        assert await service.refresh_stale_games(limit=5) == 0
        assert await service.refresh_stale_games(limit=5) == 0
        assert mock_steam_client.get_app_details.await_count == 1

        steam_cooldown.reset()
        assert await service.refresh_stale_games(limit=5) == 1
        assert (await service.repo.get_by_id(1)).genres == ["Simulation", "Strategy"]


@pytest.mark.asyncio
async def test_review_rate_limit_starts_cooldown(test_db, mock_steam_client):
    """A 429 from appreviews (same IP budget) also pauses Steam lookups; the
    game is still saved without review data."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        mock_steam_client.get_app_details = AsyncMock(return_value=STEAM_GAME_WITH_GENRES)
        mock_steam_client.get_app_reviews = AsyncMock(side_effect=SteamAPIRateLimitError("429"))

        game = await service.get_or_fetch_game(367520)

        assert game is not None and game.review_score == 0
        assert steam_cooldown.active


def test_steam_cooldown_expires():
    """The pause ends once its duration has elapsed."""
    cooldown = SteamCooldown(seconds=0.0)
    cooldown.trip()
    assert cooldown.active is False
    long = SteamCooldown(seconds=60.0)
    assert long.active is False
    long.trip()
    assert long.active is True
    long.reset()
    assert long.active is False


@pytest.mark.asyncio
async def test_mark_unavailable_keeps_fetched_genres(test_db, mock_steam_client):
    """Genres fetched earlier are not wiped when Steam later reports the app unavailable."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        await service.repo.create(
            id=56, name="Was here", type="game", genres=["RPG"], categories=["Single-player"],
            last_refreshed_at=utcnow() - timedelta(days=30),
        )
        await session.commit()

        returned = await service.get_or_fetch_game(56)
        game = await service.repo.get_by_id(56)

        assert returned is game

        assert game.genres == ["RPG"]
        assert game.categories == ["Single-player"]
        assert game.needs_refresh is False


@pytest.mark.asyncio
async def test_get_genre_counts_maps_rows(test_db, mock_steam_client):
    """The service shapes the repository's (name, count) tuples as dicts."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        await service.repo.create(id=1, name="A", type="game", genres=["Action", "Indie"])
        await service.repo.create(id=2, name="B", type="game", genres=["Action"])
        await session.commit()

        assert await service.get_genre_counts() == [
            {"name": "Action", "count": 2},
            {"name": "Indie", "count": 1},
        ]


@pytest.mark.asyncio
async def test_review_rate_limit_keeps_cached_reviews_on_update(test_db, mock_steam_client):
    """A throttled appreviews call on an existing row keeps its review data and
    its refresh time (so a stale row is retried after the cool-down), while
    the genres and categories from appdetails are still stored."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        old = utcnow() - timedelta(days=30)
        await service.repo.create(
            id=367520, name="Old name", type="game", review_score=9,
            total_positive=900, total_negative=100, total_reviews=1000,
            last_refreshed_at=old,
        )
        await session.commit()
        mock_steam_client.get_app_details = AsyncMock(return_value=STEAM_GAME_WITH_GENRES)
        mock_steam_client.get_app_reviews = AsyncMock(side_effect=SteamAPIRateLimitError("429"))

        game = await service.get_or_fetch_game(367520)

        assert steam_cooldown.active
        assert game.genres == ["Action", "Adventure", "Indie"]
        assert game.name == "Hollow Knight"
        assert (game.review_score, game.total_positive, game.total_negative, game.total_reviews) == (
            9, 900, 100, 1000,
        )
        assert game.last_refreshed_at.replace(tzinfo=None) == old.replace(tzinfo=None)
        assert game.needs_refresh is True


@pytest.mark.asyncio
async def test_review_generic_error_keeps_cached_reviews_and_marks_refreshed(
    test_db, mock_steam_client
):
    """A non-throttle review failure keeps the cached reviews but records the
    refresh, so the row is not refetched on every call."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        await service.repo.create(
            id=367520, name="Old", type="game", review_score=7,
            total_positive=70, total_negative=30, total_reviews=100,
            last_refreshed_at=utcnow() - timedelta(days=30),
        )
        await session.commit()
        mock_steam_client.get_app_details = AsyncMock(return_value=STEAM_GAME_WITH_GENRES)
        mock_steam_client.get_app_reviews = AsyncMock(side_effect=SteamAPIError("500"))

        game = await service.get_or_fetch_game(367520)

        assert not steam_cooldown.active
        assert (game.review_score, game.total_reviews) == (7, 100)
        assert game.needs_refresh is False


@pytest.mark.asyncio
async def test_review_success_updates_reviews_on_existing_row(test_db, mock_steam_client):
    """Control: when appreviews answers, the existing row's reviews are replaced."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        await service.repo.create(
            id=367520, name="Old", type="game", review_score=2, total_reviews=10,
            last_refreshed_at=utcnow() - timedelta(days=30),
        )
        await session.commit()
        mock_steam_client.get_app_details = AsyncMock(return_value=STEAM_GAME_WITH_GENRES)
        mock_steam_client.get_app_reviews = AsyncMock(return_value={
            "review_score": 9, "total_positive": 90, "total_negative": 10,
        })

        game = await service.get_or_fetch_game(367520)

        assert (game.review_score, game.total_reviews) == (9, 100)


@pytest.mark.asyncio
async def test_refresh_stale_games_stops_after_review_rate_limit(test_db, mock_steam_client):
    """A 429 from appreviews during a batch stops it before the next appdetails call."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        for app_id in (1, 2):
            await service.repo.create(
                id=app_id, name=f"G{app_id}", type="game",
                last_refreshed_at=utcnow() - timedelta(days=30 + app_id),
            )
        await session.commit()
        mock_steam_client.get_app_details = AsyncMock(return_value=STEAM_GAME_WITH_GENRES)
        mock_steam_client.get_app_reviews = AsyncMock(side_effect=SteamAPIRateLimitError("429"))

        count = await service.refresh_stale_games(limit=10)

        # The throttled row kept its refresh time, so it is not counted as
        # refreshed, but its appdetails fields were stored and committed.
        assert count == 0
        assert mock_steam_client.get_app_details.await_count == 1
        await session.rollback()
        first = await service.repo.get_by_id(2)  # oldest refresh goes first
        assert first.genres == ["Action", "Adventure", "Indie"]
        assert (await service.repo.get_by_id(1)).genres is None


@pytest.mark.asyncio
async def test_refresh_game_reports_each_outcome(test_db, mock_steam_client):
    """refresh_game tells the caller whether Steam was actually reached."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        old = utcnow() - timedelta(days=30)
        await service.repo.create(id=367520, name="Old", type="game", last_refreshed_at=old)
        await session.commit()

        # Cool-down active: no Steam call, cached row, retry delay given.
        steam_cooldown.trip()
        outcome = await service.refresh_game(367520)
        assert outcome.status is FetchStatus.RATE_LIMITED and outcome.refreshed is False
        assert outcome.game is not None and 0 < outcome.retry_after_seconds <= 180
        mock_steam_client.get_app_details.assert_not_awaited()
        steam_cooldown.reset()

        # Throttled by this very request.
        mock_steam_client.get_app_details = AsyncMock(side_effect=SteamAPIRateLimitError("429"))
        outcome = await service.refresh_game(367520)
        assert outcome.status is FetchStatus.RATE_LIMITED and outcome.retry_after_seconds > 0
        steam_cooldown.reset()

        # Other Steam error.
        mock_steam_client.get_app_details = AsyncMock(side_effect=SteamAPIError("500"))
        outcome = await service.refresh_game(367520)
        assert outcome.status is FetchStatus.FAILED and outcome.retry_after_seconds is None

        # Unavailable on Steam: cached row kept, not reported refreshed.
        mock_steam_client.get_app_details = AsyncMock(return_value=None)
        outcome = await service.refresh_game(367520)
        assert outcome.status is FetchStatus.UNAVAILABLE and outcome.game is not None
        assert outcome.refreshed is False

        # Success, even though the row was just marked checked (forced).
        mock_steam_client.get_app_details = AsyncMock(return_value=STEAM_GAME_WITH_GENRES)
        outcome = await service.refresh_game(367520)
        assert outcome.refreshed is True
        assert outcome.game.genres == ["Action", "Adventure", "Indie"]


def test_steam_cooldown_remaining_seconds():
    """remaining_seconds is 0 when inactive and rounds up while active."""
    cooldown = SteamCooldown(seconds=60.0)
    assert cooldown.remaining_seconds == 0
    cooldown.trip()
    assert 59 <= cooldown.remaining_seconds <= 60
    cooldown.reset()
    assert cooldown.remaining_seconds == 0


@pytest.mark.asyncio
async def test_refresh_game_review_rate_limit_is_not_reported_refreshed(test_db, mock_steam_client):
    """appdetails succeeds but appreviews is throttled: the genres are saved,
    yet the refresh is RATE_LIMITED with the cool-down delay, not REFRESHED."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        old = utcnow() - timedelta(days=30)
        await service.repo.create(
            id=367520, name="Old", type="game", review_score=9,
            total_positive=900, total_negative=100, total_reviews=1000,
            last_refreshed_at=old,
        )
        await session.commit()
        mock_steam_client.get_app_details = AsyncMock(return_value=STEAM_GAME_WITH_GENRES)
        mock_steam_client.get_app_reviews = AsyncMock(side_effect=SteamAPIRateLimitError("429"))

        outcome = await service.refresh_game(367520)

        assert outcome.status is FetchStatus.RATE_LIMITED
        assert outcome.refreshed is False
        assert outcome.retry_after_seconds is not None and 0 < outcome.retry_after_seconds <= 180
        assert outcome.game.genres == ["Action", "Adventure", "Indie"]
        assert outcome.game.review_score == 9
        assert outcome.game.last_refreshed_at.replace(tzinfo=None) == old.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_get_or_fetch_game_serves_recent_legacy_row_without_steam_call(
    test_db, mock_steam_client
):
    """A row refreshed recently but cached before genres were stored (genres
    NULL) is a cache hit on the read-through path: after an upgrade, sync and
    page loads must not refetch the whole legacy cache. It stays in the
    background refresh queue (needs_refresh) for refresh_stale_games."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        for app_id in range(1, 51):
            await service.repo.create(
                id=app_id, name=f"G{app_id}", type="game", review_score=8,
                header_image=f"https://example.invalid/{app_id}.jpg",
                last_refreshed_at=utcnow() - timedelta(days=2),
            )
        await session.commit()

        games = [await service.get_or_fetch_game(app_id) for app_id in range(1, 51)]

        assert all(g is not None and g.review_score == 8 and g.genres is None for g in games)
        mock_steam_client.get_app_details.assert_not_called()
        mock_steam_client.get_app_reviews.assert_not_called()
        assert all(g.needs_refresh for g in games)
        assert len(await service.repo.get_stale_games()) == 50


@pytest.mark.asyncio
async def test_bulk_cache_games_skips_recent_legacy_rows(test_db, mock_steam_client):
    """bulk_cache_games uses the same age rule as get_or_fetch_game: a recent
    row with genres NULL is skipped (left to refresh_stale_games)."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        await service.repo.create(
            id=1, name="Legacy", type="game", last_refreshed_at=utcnow() - timedelta(hours=1),
        )
        await session.commit()

        assert await service.bulk_cache_games([1]) == 0
        mock_steam_client.get_app_details.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limit_is_not_hammered_by_successive_lookups(test_db, mock_steam_client):
    """Once Steam has throttled a lookup, further stale lookups in the same
    window serve the cache instead of sending requests that extend the ban."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        for app_id in (1, 2, 3):
            await service.repo.create(
                id=app_id, name=f"G{app_id}", type="game",
                last_refreshed_at=utcnow() - timedelta(days=30),
            )
        await session.commit()
        mock_steam_client.get_app_details = AsyncMock(side_effect=SteamAPIRateLimitError("429"))

        results = [await service.get_or_fetch_game(app_id) for app_id in (1, 2, 3)]

        assert all(r is not None for r in results)
        assert mock_steam_client.get_app_details.await_count == 1


@pytest.mark.asyncio
async def test_lookup_game_reports_how_the_row_was_got(test_db, mock_steam_client):
    """lookup_game tells a cache hit (None), a cool-down skip on an uncached
    app (None row, RATE_LIMITED, no Steam call) and Steam not serving the app
    (None row, UNAVAILABLE) apart; get_or_fetch_game returns None for both."""
    async with test_db() as session:
        service = GameService(session, mock_steam_client)
        await service.repo.create(id=1, name="Fresh", type="game", last_refreshed_at=utcnow())
        await session.commit()

        game, status = await service.lookup_game(1)
        assert game is not None and game.id == 1 and status is None
        mock_steam_client.get_app_details.assert_not_awaited()

        steam_cooldown.trip()
        assert 0 < service.steam_retry_after_seconds() <= 180
        game, status = await service.lookup_game(12345)
        assert game is None and status is FetchStatus.RATE_LIMITED
        mock_steam_client.get_app_details.assert_not_awaited()
        steam_cooldown.reset()
        assert service.steam_retry_after_seconds() == 0

        mock_steam_client.get_app_details = AsyncMock(return_value=None)
        game, status = await service.lookup_game(12345)
        assert game is None and status is FetchStatus.UNAVAILABLE
        assert await service.get_or_fetch_game(12345) is None
