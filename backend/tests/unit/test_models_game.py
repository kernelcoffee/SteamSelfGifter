"""Unit tests for Game model.

This module contains comprehensive tests for the Game model, including:
- Basic creation with minimal and complete fields
- Timestamp and review data handling
- Bundle-specific functionality
- Computed properties (review_percentage, needs_refresh)
- Cache and refresh mechanics
- Different game types (game, dlc, bundle)
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models.base import Base
from models.game import Game


@pytest.fixture
def engine():
    """Create an in-memory SQLite database for testing.

    Returns:
        Engine: SQLAlchemy engine connected to in-memory database with all tables created.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    """Create a new database session for each test.

    Args:
        engine: SQLAlchemy engine fixture.

    Yields:
        Session: Database session that rolls back after each test.
    """
    with Session(engine) as session:
        yield session
        session.rollback()


def test_game_creation_with_minimal_fields(session):
    """Test creating Game with only required fields"""
    # GIVEN: A database session is available
    # WHEN: Creating a game with only id, name, and type
    # THEN: The game is created with defaults for optional fields

    game = Game(id=1234567, name="Test Game", type="game")
    session.add(game)
    session.commit()

    assert game.id == 1234567
    assert game.name == "Test Game"
    assert game.type == "game"
    assert game.is_bundle is False
    # needs_refresh should be True when never refreshed
    assert game.needs_refresh is True


def test_game_creation_with_all_fields(session):
    """Test creating Game with all fields populated"""
    # GIVEN: A database session is available
    # WHEN: Creating a game with all fields populated
    # THEN: All fields are correctly stored and needs_refresh is False due to recent refresh

    game = Game(
        id=7654321,
        name="Complete Game",
        type="game",
        release_date="2023-01-15",
        review_score=8,
        total_positive=1500,
        total_negative=200,
        total_reviews=1700,
        is_bundle=False,
        last_refreshed_at=datetime.utcnow(),
        description="A great game",
        price=1999,  # $19.99
    )
    session.add(game)
    session.commit()

    assert game.id == 7654321
    assert game.name == "Complete Game"
    assert game.release_date == "2023-01-15"
    assert game.review_score == 8
    assert game.total_reviews == 1700
    # needs_refresh should be False when recently refreshed
    assert game.needs_refresh is False
    assert game.price == 1999


def test_game_timestamps(session):
    """Test that timestamps are automatically created"""
    # GIVEN: A database session is available
    # WHEN: Creating and saving a new game
    # THEN: Timestamps are automatically set to the same value

    game = Game(id=111111, name="Timestamp Game", type="game")
    session.add(game)
    session.commit()

    assert isinstance(game.created_at, datetime)
    assert isinstance(game.updated_at, datetime)
    assert game.created_at == game.updated_at


def test_game_review_data(session):
    """Test game review data fields"""
    # GIVEN: A database session is available
    # WHEN: Creating a game with review score and statistics
    # THEN: All review data fields are correctly stored

    game = Game(
        id=222222,
        name="Popular Game",
        type="game",
        review_score=9,
        total_positive=10000,
        total_negative=500,
        total_reviews=10500,
    )
    session.add(game)
    session.commit()

    assert game.review_score == 9
    assert game.total_positive == 10000
    assert game.total_negative == 500
    assert game.total_reviews == 10500


def test_game_bundle_fields(session):
    """Test bundle-specific fields"""
    # GIVEN: A database session is available
    # WHEN: Creating a bundle with content list and game_id
    # THEN: Bundle-specific fields are correctly stored

    game = Game(
        id=333333,
        name="Game Bundle",
        type="bundle",
        is_bundle=True,
        bundle_content=[123, 456, 789],
        game_id=123,
    )
    session.add(game)
    session.commit()

    assert game.is_bundle is True
    assert game.bundle_content == [123, 456, 789]
    assert game.game_id == 123


def test_game_repr(session):
    """Test string representation of Game"""
    # GIVEN: A game exists in the database
    # WHEN: Getting the string representation of the game
    # THEN: The repr includes key identifying information

    game = Game(id=444444, name="Repr Game", type="dlc")
    session.add(game)
    session.commit()

    repr_str = repr(game)
    assert "Game" in repr_str
    assert "444444" in repr_str
    assert "Repr Game" in repr_str
    assert "dlc" in repr_str


def test_review_percentage_property(session):
    """Test review_percentage calculation"""
    # GIVEN: A game with 850 positive and 150 negative reviews
    # WHEN: Accessing the review_percentage property
    # THEN: The percentage is correctly calculated as 85.0%

    game = Game(
        id=555555,
        name="Review Test",
        type="game",
        total_positive=850,
        total_negative=150,
        total_reviews=1000,
    )
    session.add(game)
    session.commit()

    assert game.review_percentage == 85.0


def test_review_percentage_with_no_reviews(session):
    """Test review_percentage when there are no reviews"""
    # GIVEN: Games with no review data or zero reviews
    # WHEN: Accessing the review_percentage property
    # THEN: The percentage is None for games without reviews

    game1 = Game(id=666666, name="No Reviews", type="game")
    game2 = Game(
        id=777777,
        name="Zero Reviews",
        type="game",
        total_positive=0,
        total_negative=0,
        total_reviews=0,
    )
    session.add_all([game1, game2])
    session.commit()

    assert game1.review_percentage is None
    assert game2.review_percentage is None


def test_needs_refresh_property_never_refreshed(session):
    """Test needs_refresh when game was never refreshed"""
    # GIVEN: A game that has never been refreshed (last_refreshed_at is None)
    # WHEN: Checking the needs_refresh property
    # THEN: The property returns True indicating refresh is needed

    game = Game(id=888888, name="Never Refreshed", type="game")
    session.add(game)
    session.commit()

    assert game.needs_refresh is True


def test_needs_refresh_property_recently_refreshed(session):
    """Test needs_refresh when game was recently refreshed"""
    # GIVEN: A game that was refreshed 3 days ago (within 7 day threshold)
    # WHEN: Checking the needs_refresh property
    # THEN: The property returns False indicating no refresh needed

    game = Game(
        id=999999,
        name="Recently Refreshed",
        type="game",
        last_refreshed_at=datetime.utcnow() - timedelta(days=3),
    )
    session.add(game)
    session.commit()

    assert game.needs_refresh is False


def test_needs_refresh_property_stale_data(session):
    """Test needs_refresh when game data is stale (older than 7 days)"""
    # GIVEN: A game that was refreshed 10 days ago (beyond 7 day threshold)
    # WHEN: Checking the needs_refresh property
    # THEN: The property returns True indicating refresh is needed

    game = Game(
        id=101010,
        name="Stale Data",
        type="game",
        last_refreshed_at=datetime.utcnow() - timedelta(days=10),
    )
    session.add(game)
    session.commit()

    assert game.needs_refresh is True


def test_game_types(session):
    """Test different game types"""
    # GIVEN: A database session is available
    # WHEN: Creating games with different types (game, dlc, bundle)
    # THEN: Each game type is correctly stored

    game1 = Game(id=111, name="Base Game", type="game")
    game2 = Game(id=222, name="DLC Content", type="dlc")
    game3 = Game(id=333, name="Bundle Pack", type="bundle")

    session.add_all([game1, game2, game3])
    session.commit()

    assert game1.type == "game"
    assert game2.type == "dlc"
    assert game3.type == "bundle"


def test_nullable_fields(session):
    """Test that optional fields have expected defaults"""
    # GIVEN: A database session is available
    # WHEN: Creating a game with only required fields
    # THEN: Optional fields have their default values (0 for review stats, None for others)

    game = Game(id=121212, name="Minimal Game", type="game")
    session.add(game)
    session.commit()

    assert game.release_date is None
    # Review fields have defaults of 0 (not None)
    assert game.review_score == 0
    assert game.total_positive == 0
    assert game.total_negative == 0
    assert game.total_reviews == 0
    assert game.bundle_content is None
    assert game.game_id is None
    assert game.last_refreshed_at is None
    assert game.description is None
    assert game.price is None


def test_cache_fields(session):
    """Test cache-related fields"""
    # GIVEN: A database session is available
    # WHEN: Creating a game with last_refreshed_at set to current time
    # THEN: The needs_refresh property returns False

    game = Game(
        id=131313,
        name="Cached Game",
        type="game",
        last_refreshed_at=datetime.utcnow(),
    )
    session.add(game)
    session.commit()

    # needs_refresh should be False when recently refreshed
    assert game.needs_refresh is False
    assert isinstance(game.last_refreshed_at, datetime)


def test_game_update(session):
    """Test updating game data"""
    # GIVEN: An existing game in the database
    # WHEN: Updating game fields and setting last_refreshed_at
    # THEN: All updates are persisted and needs_refresh changes accordingly

    game = Game(id=141414, name="Old Name", type="game")
    session.add(game)
    session.commit()

    # Verify initially needs refresh (no refresh date)
    assert game.needs_refresh is True

    # Update game data
    game.name = "New Name"
    game.review_score = 7
    game.last_refreshed_at = datetime.utcnow()
    session.commit()

    # Verify updates
    retrieved = session.query(Game).filter_by(id=141414).first()
    assert retrieved.name == "New Name"
    assert retrieved.review_score == 7
    assert retrieved.needs_refresh is False  # Recently refreshed
    assert retrieved.last_refreshed_at is not None


def test_game_with_dlc_type(session):
    """Test creating a DLC entry"""
    # GIVEN: A database session is available
    # WHEN: Creating a game with type 'dlc' and a price
    # THEN: The DLC is correctly stored with all its properties

    dlc = Game(
        id=151515,
        name="Test DLC",
        type="dlc",
        release_date="2024-05-01",
        price=999,  # $9.99
    )
    session.add(dlc)
    session.commit()

    assert dlc.type == "dlc"
    assert dlc.name == "Test DLC"
    assert dlc.price == 999


def test_needs_refresh_property_computed(session):
    """Test that needs_refresh is a computed property and cannot be set"""
    # GIVEN: A game exists in the database
    # WHEN: Attempting to set the needs_refresh property directly
    # THEN: An AttributeError is raised as it's a read-only computed property

    game = Game(id=161616, name="Refresh Test", type="game")
    session.add(game)
    session.commit()

    # Should need refresh when never refreshed
    assert game.needs_refresh is True

    # Update last_refreshed_at - needs_refresh should automatically become False
    game.last_refreshed_at = datetime.utcnow()
    session.commit()
    assert game.needs_refresh is False

    # Verify needs_refresh cannot be set directly (it's a property)
    with pytest.raises(AttributeError):
        game.needs_refresh = True
