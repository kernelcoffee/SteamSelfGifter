"""Unit tests for BaseRepository.

Tests the generic repository pattern with common CRUD operations for
async SQLAlchemy models.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.exc import MultipleResultsFound

from models.base import Base
from models.game import Game
from repositories.base import BaseRepository


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
    Create a BaseRepository instance for Game model.

    Args:
        session: Database session fixture.

    Returns:
        BaseRepository[Game]: Repository instance for testing.
    """
    return BaseRepository(Game, session)


@pytest.mark.asyncio
async def test_create_record(game_repo, session):
    """Test creating a new record."""
    # GIVEN: A repository instance
    # WHEN: A new record is created
    # THEN: The record should be persisted with correct values

    game = await game_repo.create(
        id=730, name="Counter-Strike 2", type="game"
    )
    await session.commit()

    assert game.id == 730
    assert game.name == "Counter-Strike 2"
    assert game.type == "game"


@pytest.mark.asyncio
async def test_get_by_id(game_repo, session):
    """Test retrieving a record by primary key."""
    # GIVEN: An existing record in the database
    # WHEN: The record is retrieved by ID
    # THEN: The correct record should be returned

    await game_repo.create(id=730, name="CS2", type="game")
    await session.commit()

    game = await game_repo.get_by_id(730)
    assert game is not None
    assert game.id == 730
    assert game.name == "CS2"


@pytest.mark.asyncio
async def test_get_by_id_not_found(game_repo):
    """Test retrieving a non-existent record."""
    # GIVEN: An empty database
    # WHEN: A non-existent ID is requested
    # THEN: None should be returned

    game = await game_repo.get_by_id(999)
    assert game is None


@pytest.mark.asyncio
async def test_get_all(game_repo, session):
    """Test retrieving all records."""
    # GIVEN: Multiple records in the database
    # WHEN: All records are retrieved
    # THEN: All records should be returned

    await game_repo.create(id=730, name="CS2", type="game")
    await game_repo.create(id=570, name="Dota 2", type="game")
    await game_repo.create(id=440, name="TF2", type="game")
    await session.commit()

    games = await game_repo.get_all()
    assert len(games) == 3


@pytest.mark.asyncio
async def test_get_all_with_limit(game_repo, session):
    """Test retrieving records with pagination limit."""
    # GIVEN: Multiple records in the database
    # WHEN: Records are retrieved with a limit
    # THEN: Only the specified number of records should be returned

    await game_repo.create(id=730, name="CS2", type="game")
    await game_repo.create(id=570, name="Dota 2", type="game")
    await game_repo.create(id=440, name="TF2", type="game")
    await session.commit()

    games = await game_repo.get_all(limit=2)
    assert len(games) == 2


@pytest.mark.asyncio
async def test_get_all_with_offset(game_repo, session):
    """Test retrieving records with pagination offset."""
    # GIVEN: Multiple records in the database
    # WHEN: Records are retrieved with an offset
    # THEN: The correct number of records after offset should be returned

    await game_repo.create(id=730, name="CS2", type="game")
    await game_repo.create(id=570, name="Dota 2", type="game")
    await game_repo.create(id=440, name="TF2", type="game")
    await session.commit()

    games = await game_repo.get_all(offset=1, limit=2)
    assert len(games) == 2
    # Verify we got 2 records (ordering not guaranteed without ORDER BY)


@pytest.mark.asyncio
async def test_update_record(game_repo, session):
    """Test updating an existing record."""
    # GIVEN: An existing record in the database
    # WHEN: The record is updated
    # THEN: The changes should be persisted

    await game_repo.create(id=730, name="CS:GO", type="game")
    await session.commit()

    updated = await game_repo.update(730, name="Counter-Strike 2")
    await session.commit()

    assert updated is not None
    assert updated.name == "Counter-Strike 2"
    assert updated.id == 730


@pytest.mark.asyncio
async def test_update_nonexistent_record(game_repo):
    """Test updating a non-existent record."""
    # GIVEN: An empty database
    # WHEN: A non-existent record is updated
    # THEN: None should be returned

    updated = await game_repo.update(999, name="Test")
    assert updated is None


@pytest.mark.asyncio
async def test_delete_record(game_repo, session):
    """Test deleting a record."""
    # GIVEN: An existing record in the database
    # WHEN: The record is deleted
    # THEN: The record should be removed from the database

    await game_repo.create(id=730, name="CS2", type="game")
    await session.commit()

    deleted = await game_repo.delete(730)
    await session.commit()

    assert deleted is True
    game = await game_repo.get_by_id(730)
    assert game is None


@pytest.mark.asyncio
async def test_delete_nonexistent_record(game_repo):
    """Test deleting a non-existent record."""
    # GIVEN: An empty database
    # WHEN: A non-existent record is deleted
    # THEN: False should be returned

    deleted = await game_repo.delete(999)
    assert deleted is False


@pytest.mark.asyncio
async def test_count(game_repo, session):
    """Test counting records."""
    # GIVEN: Multiple records in the database
    # WHEN: The count is retrieved
    # THEN: The correct count should be returned

    await game_repo.create(id=730, name="CS2", type="game")
    await game_repo.create(id=570, name="Dota 2", type="game")
    await session.commit()

    count = await game_repo.count()
    assert count == 2


@pytest.mark.asyncio
async def test_count_empty(game_repo):
    """Test counting records in empty table."""
    # GIVEN: An empty database
    # WHEN: The count is retrieved
    # THEN: Zero should be returned

    count = await game_repo.count()
    assert count == 0


@pytest.mark.asyncio
async def test_exists(game_repo, session):
    """Test checking if record exists."""
    # GIVEN: An existing record in the database
    # WHEN: Existence is checked
    # THEN: True should be returned

    await game_repo.create(id=730, name="CS2", type="game")
    await session.commit()

    exists = await game_repo.exists(730)
    assert exists is True


@pytest.mark.asyncio
async def test_exists_not_found(game_repo):
    """Test checking if non-existent record exists."""
    # GIVEN: An empty database
    # WHEN: Existence of non-existent record is checked
    # THEN: False should be returned

    exists = await game_repo.exists(999)
    assert exists is False


@pytest.mark.asyncio
async def test_bulk_create(game_repo, session):
    """Test creating multiple records at once."""
    # GIVEN: A list of record data
    # WHEN: Records are bulk created
    # THEN: All records should be persisted

    games_data = [
        {"id": 730, "name": "CS2", "type": "game"},
        {"id": 570, "name": "Dota 2", "type": "game"},
        {"id": 440, "name": "TF2", "type": "game"},
    ]

    games = await game_repo.bulk_create(games_data)
    await session.commit()

    assert len(games) == 3
    assert games[0].name == "CS2"
    assert games[1].name == "Dota 2"
    assert games[2].name == "TF2"


@pytest.mark.asyncio
async def test_filter_by(game_repo, session):
    """Test filtering records by field values."""
    # GIVEN: Multiple records with different field values
    # WHEN: Records are filtered by a specific field
    # THEN: Only matching records should be returned

    await game_repo.create(id=730, name="CS2", type="game")
    await game_repo.create(id=570, name="Dota 2", type="game")
    await game_repo.create(id=1001, name="CS2 DLC", type="dlc")
    await session.commit()

    games = await game_repo.filter_by(type="game")
    assert len(games) == 2

    dlcs = await game_repo.filter_by(type="dlc")
    assert len(dlcs) == 1


@pytest.mark.asyncio
async def test_filter_by_multiple_fields(game_repo, session):
    """Test filtering by multiple field values."""
    # GIVEN: Multiple records with different field combinations
    # WHEN: Records are filtered by multiple fields
    # THEN: Only records matching all criteria should be returned

    await game_repo.create(id=730, name="CS2", type="game", review_score=9)
    await game_repo.create(id=570, name="Dota 2", type="game", review_score=8)
    await game_repo.create(id=440, name="TF2", type="game", review_score=9)
    await session.commit()

    games = await game_repo.filter_by(type="game", review_score=9)
    assert len(games) == 2


@pytest.mark.asyncio
async def test_get_one_or_none_found(game_repo, session):
    """Test getting a single record that exists."""
    # GIVEN: A single matching record in the database
    # WHEN: A record is retrieved by unique field
    # THEN: The record should be returned

    await game_repo.create(id=730, name="CS2", type="game")
    await session.commit()

    game = await game_repo.get_one_or_none(id=730)
    assert game is not None
    assert game.id == 730


@pytest.mark.asyncio
async def test_get_one_or_none_not_found(game_repo):
    """Test getting a single record that doesn't exist."""
    # GIVEN: An empty database
    # WHEN: A non-existent record is requested
    # THEN: None should be returned

    game = await game_repo.get_one_or_none(id=999)
    assert game is None


@pytest.mark.asyncio
async def test_get_one_or_none_multiple_results(game_repo, session):
    """Test getting a single record when multiple match."""
    # GIVEN: Multiple records matching the criteria
    # WHEN: A single record is requested
    # THEN: MultipleResultsFound exception should be raised

    await game_repo.create(id=730, name="CS2", type="game")
    await game_repo.create(id=570, name="Dota 2", type="game")
    await session.commit()

    with pytest.raises(MultipleResultsFound):
        await game_repo.get_one_or_none(type="game")
