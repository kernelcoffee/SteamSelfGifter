"""Unit tests for Giveaway model.

This module contains comprehensive tests for the Giveaway model, including:
- Basic creation with minimal and complete fields
- Timestamp handling and unique code constraint
- Status properties (is_active, is_expired)
- Time calculations (time_remaining)
- Safety scoring and entry tracking
- Foreign key relationships with Game model
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models.base import Base
from models.game import Game
from models.giveaway import Giveaway


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


def test_giveaway_creation_with_minimal_fields(session):
    """Test creating Giveaway with only required fields"""
    # GIVEN: A database session is available
    # WHEN: Creating a giveaway with only required fields
    # THEN: The giveaway is created with default values for optional fields

    giveaway = Giveaway(
        code="ABC123",
        url="/giveaway/ABC123/test-game",
        game_name="Test Game",
        price=50,
    )
    session.add(giveaway)
    session.commit()

    assert giveaway.id is not None
    assert giveaway.code == "ABC123"
    assert giveaway.url == "/giveaway/ABC123/test-game"
    assert giveaway.game_name == "Test Game"
    assert giveaway.price == 50
    assert giveaway.copies == 1
    assert giveaway.is_hidden is False
    assert giveaway.is_entered is False


def test_giveaway_creation_with_all_fields(session):
    """Test creating Giveaway with all fields populated"""
    # GIVEN: A database session is available
    # WHEN: Creating a giveaway with all fields populated including safety and entry data
    # THEN: All fields are correctly stored

    end_time = datetime.utcnow() + timedelta(days=7)
    entered_at = datetime.utcnow()

    giveaway = Giveaway(
        code="XYZ789",
        url="/giveaway/XYZ789/complete-game",
        game_id=123456,
        game_name="Complete Game",
        price=100,
        copies=5,
        end_time=end_time,
        is_hidden=False,
        is_entered=True,
        is_safe=True,
        safety_score=95,
        entered_at=entered_at,
    )
    session.add(giveaway)
    session.commit()

    assert giveaway.code == "XYZ789"
    assert giveaway.game_id == 123456
    assert giveaway.copies == 5
    assert giveaway.end_time == end_time
    assert giveaway.is_entered is True
    assert giveaway.is_safe is True
    assert giveaway.safety_score == 95
    assert giveaway.entered_at == entered_at


def test_giveaway_timestamps(session):
    """Test that timestamps are automatically created"""
    # GIVEN: A database session is available
    # WHEN: Creating and saving a new giveaway
    # THEN: Timestamps (created_at, updated_at, discovered_at) are automatically set

    giveaway = Giveaway(code="TIME123", url="/test", game_name="Test", price=10)
    session.add(giveaway)
    session.commit()

    assert isinstance(giveaway.created_at, datetime)
    assert isinstance(giveaway.updated_at, datetime)
    assert giveaway.created_at == giveaway.updated_at
    assert isinstance(giveaway.discovered_at, datetime)


def test_giveaway_unique_code(session):
    """Test that giveaway code must be unique"""
    # GIVEN: A giveaway with code "UNIQUE1" already exists in the database
    # WHEN: Attempting to create another giveaway with the same code
    # THEN: An IntegrityError is raised due to unique constraint violation

    giveaway1 = Giveaway(code="UNIQUE1", url="/test1", game_name="Game 1", price=10)
    giveaway2 = Giveaway(code="UNIQUE1", url="/test2", game_name="Game 2", price=20)

    session.add(giveaway1)
    session.commit()

    session.add(giveaway2)
    with pytest.raises(IntegrityError):
        session.commit()


def test_giveaway_repr(session):
    """Test string representation of Giveaway"""
    # GIVEN: A giveaway exists in the database
    # WHEN: Getting the string representation of the giveaway
    # THEN: The repr includes key identifying information (code, name, price)

    giveaway = Giveaway(code="REPR123", url="/test", game_name="Repr Game", price=75)
    session.add(giveaway)
    session.commit()

    repr_str = repr(giveaway)
    assert "Giveaway" in repr_str
    assert "REPR123" in repr_str
    assert "Repr Game" in repr_str
    assert "75" in repr_str


def test_is_active_property_active_giveaway(session):
    """Test is_active property for active giveaway"""
    # GIVEN: A giveaway with end_time 24 hours in the future
    # WHEN: Checking the is_active and is_expired properties
    # THEN: is_active is True and is_expired is False

    future_time = datetime.utcnow() + timedelta(hours=24)
    giveaway = Giveaway(
        code="ACTIVE1",
        url="/test",
        game_name="Active Game",
        price=50,
        end_time=future_time,
    )
    session.add(giveaway)
    session.commit()

    assert giveaway.is_active is True
    assert giveaway.is_expired is False


def test_is_expired_property(session):
    """Test is_expired for giveaway with past end_time"""
    # GIVEN: A giveaway with end_time 1 hour in the past
    # WHEN: Checking the is_active and is_expired properties
    # THEN: is_active is False and is_expired is True

    past_time = datetime.utcnow() - timedelta(hours=1)
    giveaway = Giveaway(
        code="EXPIRED1",
        url="/test",
        game_name="Expired Game",
        price=50,
        end_time=past_time,
    )
    session.add(giveaway)
    session.commit()

    assert giveaway.is_active is False
    assert giveaway.is_expired is True


def test_is_active_no_end_time(session):
    """Test is_active when end_time is None (assume active)"""
    # GIVEN: A giveaway without an end_time specified
    # WHEN: Checking the is_active property
    # THEN: is_active is True (giveaways without end_time are assumed active)

    giveaway = Giveaway(
        code="NOEND1",
        url="/test",
        game_name="No End Game",
        price=50,
        end_time=None,
    )
    session.add(giveaway)
    session.commit()

    assert giveaway.is_active is True


def test_time_remaining_property(session):
    """Test time_remaining calculation"""
    # GIVEN: A giveaway with end_time 2 hours in the future
    # WHEN: Accessing the time_remaining property
    # THEN: The property returns approximately 7200 seconds

    future_time = datetime.utcnow() + timedelta(hours=2)
    giveaway = Giveaway(
        code="TIME1",
        url="/test",
        game_name="Timed Game",
        price=50,
        end_time=future_time,
    )
    session.add(giveaway)
    session.commit()

    remaining = giveaway.time_remaining
    assert remaining is not None
    assert remaining > 0
    # Should be approximately 2 hours (7200 seconds), with small tolerance
    assert 7100 < remaining < 7300


def test_time_remaining_expired(session):
    """Test time_remaining when giveaway is expired"""
    # GIVEN: A giveaway with end_time 1 hour in the past
    # WHEN: Accessing the time_remaining property
    # THEN: The property returns 0 (not negative)

    past_time = datetime.utcnow() - timedelta(hours=1)
    giveaway = Giveaway(
        code="EXPIRED2",
        url="/test",
        game_name="Expired Game",
        price=50,
        end_time=past_time,
    )
    session.add(giveaway)
    session.commit()

    assert giveaway.time_remaining == 0


def test_time_remaining_no_end_time(session):
    """Test time_remaining when end_time is None"""
    # GIVEN: A giveaway without an end_time specified
    # WHEN: Accessing the time_remaining property
    # THEN: The property returns None

    giveaway = Giveaway(
        code="NOTIME1",
        url="/test",
        game_name="No Time Game",
        price=50,
        end_time=None,
    )
    session.add(giveaway)
    session.commit()

    assert giveaway.time_remaining is None


def test_giveaway_status_flags(session):
    """Test status flags (is_hidden, is_entered)"""
    # GIVEN: A database session is available
    # WHEN: Creating a giveaway with is_hidden and is_entered set to True
    # THEN: Both status flags are correctly stored

    giveaway = Giveaway(
        code="STATUS1",
        url="/test",
        game_name="Status Game",
        price=50,
        is_hidden=True,
        is_entered=True,
    )
    session.add(giveaway)
    session.commit()

    assert giveaway.is_hidden is True
    assert giveaway.is_entered is True


def test_giveaway_safety_fields(session):
    """Test safety-related fields"""
    # GIVEN: A database session is available
    # WHEN: Creating a giveaway with safety scoring data
    # THEN: Safety fields (is_safe, safety_score) are correctly stored

    giveaway = Giveaway(
        code="SAFE1",
        url="/test",
        game_name="Safe Game",
        price=50,
        is_safe=True,
        safety_score=90,
    )
    session.add(giveaway)
    session.commit()

    assert giveaway.is_safe is True
    assert giveaway.safety_score == 90


def test_giveaway_with_game_reference(session):
    """Test giveaway with game_id foreign key"""
    # GIVEN: A game exists in the database
    # WHEN: Creating a giveaway that references the game via game_id
    # THEN: The foreign key relationship is correctly established

    # First create a game
    game = Game(id=999888, name="Referenced Game", type="game")
    session.add(game)
    session.commit()

    # Create giveaway referencing the game
    giveaway = Giveaway(
        code="GAMEREF1",
        url="/test",
        game_id=999888,
        game_name="Referenced Game",
        price=50,
    )
    session.add(giveaway)
    session.commit()

    assert giveaway.game_id == 999888
    assert giveaway.game_name == "Referenced Game"


def test_giveaway_entry_tracking(session):
    """Test entered_at field for tracking when user entered"""
    # GIVEN: A giveaway that has not been entered yet
    # WHEN: Marking the giveaway as entered with a timestamp
    # THEN: The is_entered and entered_at fields are correctly updated

    now = datetime.utcnow()
    giveaway = Giveaway(
        code="ENTRY1",
        url="/test",
        game_name="Entry Game",
        price=50,
        is_entered=False,
    )
    session.add(giveaway)
    session.commit()

    # Initially not entered
    assert giveaway.entered_at is None

    # Mark as entered
    giveaway.is_entered = True
    giveaway.entered_at = now
    session.commit()

    assert giveaway.is_entered is True
    assert giveaway.entered_at == now


def test_computed_properties_cannot_be_set(session):
    """Test that computed properties cannot be set directly"""
    # GIVEN: A giveaway exists in the database
    # WHEN: Attempting to set computed properties directly
    # THEN: AttributeError is raised for all read-only computed properties

    giveaway = Giveaway(
        code="PROP1",
        url="/test",
        game_name="Property Game",
        price=50,
    )
    session.add(giveaway)
    session.commit()

    # Verify is_active cannot be set directly
    with pytest.raises(AttributeError):
        giveaway.is_active = False

    # Verify is_expired cannot be set directly
    with pytest.raises(AttributeError):
        giveaway.is_expired = True

    # Verify time_remaining cannot be set directly
    with pytest.raises(AttributeError):
        giveaway.time_remaining = 100


def test_giveaway_nullable_fields(session):
    """Test that optional fields can be None"""
    # GIVEN: A database session is available
    # WHEN: Creating a giveaway with only required fields
    # THEN: All optional fields default to None

    giveaway = Giveaway(
        code="NULL1",
        url="/test",
        game_name="Nullable Game",
        price=50,
    )
    session.add(giveaway)
    session.commit()

    assert giveaway.game_id is None
    assert giveaway.end_time is None
    assert giveaway.is_safe is None
    assert giveaway.safety_score is None
    assert giveaway.entered_at is None


def test_giveaway_update(session):
    """Test updating giveaway data"""
    # GIVEN: An existing giveaway in the database
    # WHEN: Updating various fields including status and safety data
    # THEN: All updates are persisted correctly

    giveaway = Giveaway(
        code="UPDATE1",
        url="/test",
        game_name="Update Game",
        price=50,
        is_hidden=False,
        is_entered=False,
    )
    session.add(giveaway)
    session.commit()

    # Update fields
    giveaway.is_hidden = True
    giveaway.is_entered = True
    giveaway.entered_at = datetime.utcnow()
    giveaway.safety_score = 85
    session.commit()

    # Verify updates
    retrieved = session.query(Giveaway).filter_by(code="UPDATE1").first()
    assert retrieved.is_hidden is True
    assert retrieved.is_entered is True
    assert retrieved.entered_at is not None
    assert retrieved.safety_score == 85


def test_giveaway_copies(session):
    """Test giveaway with multiple copies"""
    # GIVEN: A database session is available
    # WHEN: Creating a giveaway with 10 copies available
    # THEN: The copies field is correctly stored

    giveaway = Giveaway(
        code="MULTI1",
        url="/test",
        game_name="Multi Copy Game",
        price=100,
        copies=10,
    )
    session.add(giveaway)
    session.commit()

    assert giveaway.copies == 10
