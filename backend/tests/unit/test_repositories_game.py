"""Unit tests for GameRepository.

Tests the game-specific repository methods including search, cache management,
and filtering capabilities for Steam game data.
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from models.base import Base
from models.game import Game
from repositories.game import GameRepository


@pytest.fixture
async def engine():
    """
    Create an async in-memory SQLite database for testing.

    Returns:
        AsyncEngine: SQLAlchemy async engine connected to in-memory database.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine):
    """
    Create a new async database session for each test.

    Args:
        engine: SQLAlchemy async engine fixture.

    Yields:
        AsyncSession: Database session with automatic rollback after test.
    """
    AsyncSessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
def game_repo(session):
    """
    Create a GameRepository instance.

    Args:
        session: Database session fixture.

    Returns:
        GameRepository: Repository instance for testing.
    """
    return GameRepository(session)


@pytest.mark.asyncio
async def test_get_by_app_id(game_repo, session):
    """Test getting game by Steam App ID."""
    # GIVEN: An existing game in the database
    # WHEN: The game is retrieved by App ID
    # THEN: The correct game should be returned

    await game_repo.create(id=730, name="Counter-Strike 2", type="game")
    await session.commit()

    game = await game_repo.get_by_app_id(730)
    assert game is not None
    assert game.id == 730
    assert game.name == "Counter-Strike 2"


@pytest.mark.asyncio
async def test_get_by_app_id_not_found(game_repo):
    """Test getting non-existent game by App ID."""
    # GIVEN: An empty database
    # WHEN: A non-existent App ID is requested
    # THEN: None should be returned

    game = await game_repo.get_by_app_id(99999)
    assert game is None


@pytest.mark.asyncio
async def test_search_by_name(game_repo, session):
    """Test searching games by name."""
    # GIVEN: Multiple games with different names
    # WHEN: A search query is executed
    # THEN: Only matching games should be returned

    await game_repo.create(id=730, name="Counter-Strike 2", type="game")
    await game_repo.create(id=240, name="Counter-Strike: Source", type="game")
    await game_repo.create(id=570, name="Dota 2", type="game")
    await session.commit()

    results = await game_repo.search_by_name("counter-strike")
    assert len(results) == 2

    # Should be case-insensitive
    results = await game_repo.search_by_name("COUNTER")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_search_by_name_with_limit(game_repo, session):
    """Test searching with result limit."""
    # GIVEN: Multiple matching games
    # WHEN: A search is executed with a limit
    # THEN: Only the specified number of results should be returned

    await game_repo.create(id=730, name="Counter-Strike 2", type="game")
    await game_repo.create(id=240, name="Counter-Strike: Source", type="game")
    await game_repo.create(id=10, name="Counter-Strike", type="game")
    await session.commit()

    results = await game_repo.search_by_name("counter-strike", limit=2)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_get_stale_games_never_refreshed(game_repo, session):
    """Test getting games that were never refreshed."""
    # GIVEN: Games with no refresh timestamp
    # WHEN: Stale games are requested
    # THEN: Games without last_refreshed_at should be returned

    await game_repo.create(id=730, name="CS2", type="game")
    await game_repo.create(id=570, name="Dota 2", type="game")
    await session.commit()

    stale = await game_repo.get_stale_games()
    assert len(stale) == 2


@pytest.mark.asyncio
async def test_get_stale_games_old_data(game_repo, session):
    """Test getting games with old cached data."""
    # GIVEN: Games with old refresh timestamps
    # WHEN: Stale games are requested
    # THEN: Games older than threshold should be returned

    old_date = datetime.utcnow() - timedelta(days=10)
    recent_date = datetime.utcnow() - timedelta(days=3)

    await game_repo.create(
        id=730, name="CS2", type="game", last_refreshed_at=old_date
    )
    await game_repo.create(
        id=570, name="Dota 2", type="game", last_refreshed_at=recent_date
    )
    await session.commit()

    stale = await game_repo.get_stale_games(days_threshold=7)
    assert len(stale) == 1
    assert stale[0].id == 730


@pytest.mark.asyncio
async def test_get_stale_games_with_limit(game_repo, session):
    """Test getting stale games with limit."""
    # GIVEN: Multiple stale games
    # WHEN: Stale games are requested with a limit
    # THEN: Only the specified number should be returned

    await game_repo.create(id=730, name="CS2", type="game")
    await game_repo.create(id=570, name="Dota 2", type="game")
    await game_repo.create(id=440, name="TF2", type="game")
    await session.commit()

    stale = await game_repo.get_stale_games(limit=2)
    assert len(stale) == 2


@pytest.mark.asyncio
async def test_get_by_type(game_repo, session):
    """Test filtering games by type."""
    # GIVEN: Games of different types
    # WHEN: Games are filtered by type
    # THEN: Only matching type should be returned

    await game_repo.create(id=730, name="CS2", type="game")
    await game_repo.create(id=1001, name="CS2 DLC", type="dlc")
    await game_repo.create(id=1002, name="Bundle", type="bundle")
    await session.commit()

    games = await game_repo.get_by_type("game")
    assert len(games) == 1
    assert games[0].type == "game"

    dlcs = await game_repo.get_by_type("dlc")
    assert len(dlcs) == 1


@pytest.mark.asyncio
async def test_get_bundles(game_repo, session):
    """Test getting all bundles."""
    # GIVEN: Games with some marked as bundles
    # WHEN: Bundles are retrieved
    # THEN: Only bundles should be returned

    await game_repo.create(id=730, name="CS2", type="game", is_bundle=False)
    await game_repo.create(id=1001, name="Bundle 1", type="bundle", is_bundle=True)
    await game_repo.create(id=1002, name="Bundle 2", type="bundle", is_bundle=True)
    await session.commit()

    bundles = await game_repo.get_bundles()
    assert len(bundles) == 2


@pytest.mark.asyncio
async def test_get_by_main_game(game_repo, session):
    """Test getting DLCs for a main game."""
    # GIVEN: DLCs linked to a main game
    # WHEN: DLCs are retrieved by main game ID
    # THEN: Only linked DLCs should be returned

    await game_repo.create(id=730, name="CS2", type="game")
    await game_repo.create(id=1001, name="CS2 DLC 1", type="dlc", game_id=730)
    await game_repo.create(id=1002, name="CS2 DLC 2", type="dlc", game_id=730)
    await game_repo.create(id=2001, name="Other DLC", type="dlc", game_id=999)
    await session.commit()

    dlcs = await game_repo.get_by_main_game(730)
    assert len(dlcs) == 2


@pytest.mark.asyncio
async def test_get_highly_rated(game_repo, session):
    """Test getting highly rated games."""
    # GIVEN: Games with different ratings
    # WHEN: Highly rated games are requested
    # THEN: Only games meeting thresholds should be returned

    await game_repo.create(
        id=730, name="CS2", type="game", review_score=9, total_reviews=5000
    )
    await game_repo.create(
        id=570, name="Dota 2", type="game", review_score=8, total_reviews=3000
    )
    await game_repo.create(
        id=440, name="TF2", type="game", review_score=6, total_reviews=2000
    )
    await session.commit()

    highly_rated = await game_repo.get_highly_rated(min_score=7, min_reviews=1000)
    assert len(highly_rated) == 2


@pytest.mark.asyncio
async def test_get_highly_rated_with_strict_thresholds(game_repo, session):
    """Test getting highly rated games with strict criteria."""
    # GIVEN: Games with varying ratings and review counts
    # WHEN: Strict thresholds are applied
    # THEN: Only games meeting both criteria should be returned

    await game_repo.create(
        id=730, name="CS2", type="game", review_score=9, total_reviews=10000
    )
    await game_repo.create(
        id=570, name="Dota 2", type="game", review_score=9, total_reviews=500
    )
    await game_repo.create(
        id=440, name="TF2", type="game", review_score=6, total_reviews=10000
    )
    await session.commit()

    highly_rated = await game_repo.get_highly_rated(min_score=8, min_reviews=5000)
    assert len(highly_rated) == 1
    assert highly_rated[0].id == 730


@pytest.mark.asyncio
async def test_mark_refreshed(game_repo, session):
    """Test marking a game as refreshed."""
    # GIVEN: A game with no refresh timestamp
    # WHEN: The game is marked as refreshed
    # THEN: last_refreshed_at should be set to current time

    await game_repo.create(id=730, name="CS2", type="game")
    await session.commit()

    before = datetime.utcnow()
    game = await game_repo.mark_refreshed(730)
    await session.commit()
    after = datetime.utcnow()

    assert game is not None
    assert game.last_refreshed_at is not None
    assert before <= game.last_refreshed_at <= after


@pytest.mark.asyncio
async def test_mark_refreshed_nonexistent(game_repo):
    """Test marking non-existent game as refreshed."""
    # GIVEN: An empty database
    # WHEN: A non-existent game is marked as refreshed
    # THEN: None should be returned

    game = await game_repo.mark_refreshed(99999)
    assert game is None


@pytest.mark.asyncio
async def test_bulk_mark_refreshed(game_repo, session):
    """Test marking multiple games as refreshed."""
    # GIVEN: Multiple games without refresh timestamps
    # WHEN: Games are bulk marked as refreshed
    # THEN: All should have updated timestamps

    await game_repo.create(id=730, name="CS2", type="game")
    await game_repo.create(id=570, name="Dota 2", type="game")
    await game_repo.create(id=440, name="TF2", type="game")
    await session.commit()

    await game_repo.bulk_mark_refreshed([730, 570, 440])
    await session.commit()

    game1 = await game_repo.get_by_app_id(730)
    game2 = await game_repo.get_by_app_id(570)
    game3 = await game_repo.get_by_app_id(440)

    assert game1.last_refreshed_at is not None
    assert game2.last_refreshed_at is not None
    assert game3.last_refreshed_at is not None


@pytest.mark.asyncio
async def test_create_or_update_new_game(game_repo, session):
    """Test create_or_update with new game."""
    # GIVEN: An empty database
    # WHEN: create_or_update is called
    # THEN: A new game should be created

    game = await game_repo.create_or_update(730, name="CS2", type="game")
    await session.commit()

    assert game.id == 730
    assert game.name == "CS2"

    # Verify it exists
    retrieved = await game_repo.get_by_app_id(730)
    assert retrieved is not None


@pytest.mark.asyncio
async def test_create_or_update_existing_game(game_repo, session):
    """Test create_or_update with existing game."""
    # GIVEN: An existing game in the database
    # WHEN: create_or_update is called with new data
    # THEN: The existing game should be updated

    await game_repo.create(id=730, name="CS:GO", type="game")
    await session.commit()

    game = await game_repo.create_or_update(730, name="Counter-Strike 2")
    await session.commit()

    assert game.id == 730
    assert game.name == "Counter-Strike 2"


@pytest.mark.asyncio
async def test_count_by_type(game_repo, session):
    """Test counting games by type."""
    # GIVEN: Games of different types
    # WHEN: Counts are retrieved by type
    # THEN: Correct counts should be returned for each type

    await game_repo.create(id=730, name="CS2", type="game")
    await game_repo.create(id=570, name="Dota 2", type="game")
    await game_repo.create(id=1001, name="DLC 1", type="dlc")
    await game_repo.create(id=1002, name="Bundle 1", type="bundle")
    await session.commit()

    counts = await game_repo.count_by_type()

    assert counts["game"] == 2
    assert counts["dlc"] == 1
    assert counts["bundle"] == 1


@pytest.mark.asyncio
async def test_count_by_type_empty(game_repo):
    """Test counting by type with empty database."""
    # GIVEN: An empty database
    # WHEN: Counts are retrieved by type
    # THEN: Zero should be returned for all types

    counts = await game_repo.count_by_type()

    assert counts["game"] == 0
    assert counts["dlc"] == 0
    assert counts["bundle"] == 0


@pytest.mark.asyncio
async def test_get_without_reviews(game_repo, session):
    """Test getting games without review data."""
    # GIVEN: Games with and without review data
    # WHEN: Games without reviews are requested
    # THEN: Only games without reviews should be returned

    await game_repo.create(
        id=730, name="CS2", type="game", total_reviews=5000
    )
    await game_repo.create(
        id=570, name="Dota 2", type="game", total_reviews=None
    )
    await game_repo.create(
        id=440, name="TF2", type="game", total_reviews=0
    )
    await session.commit()

    without_reviews = await game_repo.get_without_reviews()
    assert len(without_reviews) == 2


@pytest.mark.asyncio
async def test_get_without_reviews_with_limit(game_repo, session):
    """Test getting games without reviews with limit."""
    # GIVEN: Multiple games without review data
    # WHEN: Games without reviews are requested with a limit
    # THEN: Only the specified number should be returned

    await game_repo.create(id=730, name="CS2", type="game")
    await game_repo.create(id=570, name="Dota 2", type="game")
    await game_repo.create(id=440, name="TF2", type="game")
    await session.commit()

    without_reviews = await game_repo.get_without_reviews(limit=2)
    assert len(without_reviews) == 2


@pytest.mark.asyncio
async def test_search_partial_match(game_repo, session):
    """Test search with partial name match."""
    # GIVEN: Games with similar names
    # WHEN: A partial search query is executed
    # THEN: All games containing the query should be returned

    await game_repo.create(id=730, name="Counter-Strike 2", type="game")
    await game_repo.create(id=570, name="Dota 2", type="game")
    await game_repo.create(id=440, name="Team Fortress 2", type="game")
    await session.commit()

    results = await game_repo.search_by_name("2")
    assert len(results) == 3  # All contain "2"


@pytest.mark.asyncio
async def test_search_no_results(game_repo, session):
    """Test search with no matching results."""
    # GIVEN: Games in the database
    # WHEN: A search query matches nothing
    # THEN: An empty list should be returned

    await game_repo.create(id=730, name="Counter-Strike 2", type="game")
    await session.commit()

    results = await game_repo.search_by_name("nonexistent")
    assert len(results) == 0
