"""Unit tests for GameService."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from models.base import Base
from models.game import Game
from services.game_service import GameService
from utils.steam_client import SteamClient, SteamAPIError


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
        game = await service.repo.create(
            id=730,
            name="CS:GO",
            type="game",
            last_refreshed_at=datetime.utcnow(),
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
        old_date = datetime.utcnow() - timedelta(days=35)
        game = await service.repo.create(
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
        game = await service.repo.create(
            id=730,
            name="Old Name",
            type="game",
            last_refreshed_at=datetime.utcnow(),
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
        old_date = datetime.utcnow() - timedelta(days=35)
        game = await service.repo.create(
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
        old_timestamp = datetime.utcnow() - timedelta(days=30)
        existing = await service.repo.create(
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
        old_date = datetime.utcnow() - timedelta(days=35)
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
        old_date = datetime.utcnow() - timedelta(days=35)
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
        fresh_date = datetime.utcnow()
        stale_date = datetime.utcnow() - timedelta(days=35)

        await service.repo.create(
            id=1, name="Fresh Game", type="game", last_refreshed_at=fresh_date
        )
        await service.repo.create(
            id=2, name="Stale Game", type="game", last_refreshed_at=stale_date
        )
        await service.repo.create(
            id=3, name="DLC", type="dlc", last_refreshed_at=fresh_date
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
            id=730, name="CS:GO", type="game", last_refreshed_at=datetime.utcnow()
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
