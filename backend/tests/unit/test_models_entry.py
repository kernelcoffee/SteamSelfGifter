"""Unit tests for Entry model.

This module contains comprehensive tests for the Entry model, including:
- Basic creation with minimal and complete fields
- Timestamp handling and default values
- Entry types (manual, auto, wishlist) and statuses (success, failed, pending)
- Computed properties (is_successful, is_failed, is_pending)
- Foreign key relationship with Giveaway model
- Points tracking and error message handling
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models.base import Base
from models.game import Game  # Import Game so foreign key resolves
from models.giveaway import Giveaway
from models.entry import Entry


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


@pytest.fixture
def giveaway(session):
    """Create a sample giveaway for testing.

    Args:
        session: Database session fixture.

    Returns:
        Giveaway: A committed giveaway instance for use in tests.
    """
    giveaway = Giveaway(
        code="TEST123",
        url="/giveaway/TEST123/test",
        game_name="Test Game",
        price=50,
    )
    session.add(giveaway)
    session.commit()
    return giveaway


def test_entry_creation_minimal(session, giveaway):
    """Test creating Entry with required fields only"""
    # GIVEN: A giveaway exists in the database
    # WHEN: Creating an entry with only required fields
    # THEN: The entry is created with defaults for optional fields

    entry = Entry(
        giveaway_id=giveaway.id,
        points_spent=50,
        entry_type="manual",
        status="success",
    )
    session.add(entry)
    session.commit()

    assert entry.id is not None
    assert entry.giveaway_id == giveaway.id
    assert entry.points_spent == 50
    assert entry.entry_type == "manual"
    assert entry.status == "success"
    assert entry.error_message is None


def test_entry_creation_complete(session, giveaway):
    """Test creating Entry with all fields populated"""
    # GIVEN: A giveaway exists in the database
    # WHEN: Creating an entry with all fields populated including error message
    # THEN: All fields are correctly stored

    now = datetime.utcnow()
    entry = Entry(
        giveaway_id=giveaway.id,
        points_spent=100,
        entry_type="auto",
        status="failed",
        entered_at=now,
        error_message="Insufficient points",
    )
    session.add(entry)
    session.commit()

    assert entry.giveaway_id == giveaway.id
    assert entry.points_spent == 100
    assert entry.entry_type == "auto"
    assert entry.status == "failed"
    assert entry.entered_at == now
    assert entry.error_message == "Insufficient points"


def test_entry_timestamps(session, giveaway):
    """Test that timestamps are automatically created"""
    # GIVEN: A giveaway exists in the database
    # WHEN: Creating and saving a new entry
    # THEN: Timestamps (created_at, updated_at, entered_at) are automatically set

    entry = Entry(
        giveaway_id=giveaway.id,
        points_spent=50,
        entry_type="manual",
        status="success",
    )
    session.add(entry)
    session.commit()

    assert isinstance(entry.created_at, datetime)
    assert isinstance(entry.updated_at, datetime)
    assert isinstance(entry.entered_at, datetime)
    assert entry.created_at == entry.updated_at


def test_entry_repr(session, giveaway):
    """Test string representation of Entry"""
    # GIVEN: An entry exists in the database
    # WHEN: Getting the string representation of the entry
    # THEN: The repr includes key identifying information (entry_id, giveaway_id, status, points)

    entry = Entry(
        giveaway_id=giveaway.id,
        points_spent=75,
        entry_type="wishlist",
        status="success",
    )
    session.add(entry)
    session.commit()

    repr_str = repr(entry)
    assert "Entry" in repr_str
    assert str(entry.id) in repr_str
    assert str(giveaway.id) in repr_str
    assert "success" in repr_str
    assert "75" in repr_str


def test_entry_with_giveaway_reference(session, giveaway):
    """Test entry with giveaway_id foreign key"""
    # GIVEN: A giveaway exists in the database
    # WHEN: Creating an entry that references the giveaway via giveaway_id
    # THEN: The foreign key relationship is correctly established

    entry = Entry(
        giveaway_id=giveaway.id,
        points_spent=50,
        entry_type="manual",
        status="success",
    )
    session.add(entry)
    session.commit()

    # Verify the foreign key relationship
    assert entry.giveaway_id == giveaway.id

    # Retrieve entry and verify relationship still valid
    retrieved = session.query(Entry).filter_by(id=entry.id).first()
    assert retrieved.giveaway_id == giveaway.id


def test_entry_types(session, giveaway):
    """Test different entry types"""
    # GIVEN: A giveaway exists in the database
    # WHEN: Creating entries with different types (manual, auto, wishlist)
    # THEN: Each entry type is correctly stored

    entry_manual = Entry(giveaway_id=giveaway.id, points_spent=50, entry_type="manual", status="success")
    entry_auto = Entry(giveaway_id=giveaway.id, points_spent=50, entry_type="auto", status="success")
    entry_wishlist = Entry(giveaway_id=giveaway.id, points_spent=50, entry_type="wishlist", status="success")

    session.add_all([entry_manual, entry_auto, entry_wishlist])
    session.commit()

    assert entry_manual.entry_type == "manual"
    assert entry_auto.entry_type == "auto"
    assert entry_wishlist.entry_type == "wishlist"


def test_entry_statuses(session, giveaway):
    """Test different entry statuses"""
    # GIVEN: A giveaway exists in the database
    # WHEN: Creating entries with different statuses (success, failed, pending)
    # THEN: Each entry status is correctly stored

    entry_success = Entry(giveaway_id=giveaway.id, points_spent=50, entry_type="manual", status="success")
    entry_failed = Entry(giveaway_id=giveaway.id, points_spent=50, entry_type="manual", status="failed")
    entry_pending = Entry(giveaway_id=giveaway.id, points_spent=50, entry_type="manual", status="pending")

    session.add_all([entry_success, entry_failed, entry_pending])
    session.commit()

    assert entry_success.status == "success"
    assert entry_failed.status == "failed"
    assert entry_pending.status == "pending"


def test_is_successful_property(session, giveaway):
    """Test is_successful property"""
    # GIVEN: Entries with different statuses exist
    # WHEN: Checking the is_successful property
    # THEN: It returns True only for entries with status "success"

    entry_success = Entry(giveaway_id=giveaway.id, points_spent=50, entry_type="manual", status="success")
    entry_failed = Entry(giveaway_id=giveaway.id, points_spent=50, entry_type="manual", status="failed")

    session.add_all([entry_success, entry_failed])
    session.commit()

    assert entry_success.is_successful is True
    assert entry_failed.is_successful is False


def test_is_failed_property(session, giveaway):
    """Test is_failed property"""
    # GIVEN: Entries with different statuses exist
    # WHEN: Checking the is_failed property
    # THEN: It returns True only for entries with status "failed"

    entry_success = Entry(giveaway_id=giveaway.id, points_spent=50, entry_type="manual", status="success")
    entry_failed = Entry(giveaway_id=giveaway.id, points_spent=50, entry_type="manual", status="failed")

    session.add_all([entry_success, entry_failed])
    session.commit()

    assert entry_success.is_failed is False
    assert entry_failed.is_failed is True


def test_is_pending_property(session, giveaway):
    """Test is_pending property"""
    # GIVEN: Entries with different statuses exist
    # WHEN: Checking the is_pending property
    # THEN: It returns True only for entries with status "pending"

    entry_success = Entry(giveaway_id=giveaway.id, points_spent=50, entry_type="manual", status="success")
    entry_pending = Entry(giveaway_id=giveaway.id, points_spent=50, entry_type="manual", status="pending")

    session.add_all([entry_success, entry_pending])
    session.commit()

    assert entry_success.is_pending is False
    assert entry_pending.is_pending is True


def test_entry_with_error_message(session, giveaway):
    """Test failed entry with error message"""
    # GIVEN: A giveaway exists in the database
    # WHEN: Creating a failed entry with an error message
    # THEN: The error message is correctly stored and is_failed is True

    entry = Entry(
        giveaway_id=giveaway.id,
        points_spent=50,
        entry_type="auto",
        status="failed",
        error_message="Giveaway already entered",
    )
    session.add(entry)
    session.commit()

    assert entry.status == "failed"
    assert entry.error_message == "Giveaway already entered"
    assert entry.is_failed is True


def test_entry_nullable_fields(session, giveaway):
    """Test that optional fields can be None"""
    # GIVEN: A giveaway exists in the database
    # WHEN: Creating an entry with only required fields
    # THEN: Optional fields (error_message) default to None

    entry = Entry(
        giveaway_id=giveaway.id,
        points_spent=50,
        entry_type="manual",
        status="success",
    )
    session.add(entry)
    session.commit()

    assert entry.error_message is None


def test_entry_update(session, giveaway):
    """Test updating entry data"""
    # GIVEN: An entry with status "pending" exists in the database
    # WHEN: Updating the status to "success"
    # THEN: The update is persisted and computed properties reflect the new status

    entry = Entry(
        giveaway_id=giveaway.id,
        points_spent=50,
        entry_type="manual",
        status="pending",
    )
    session.add(entry)
    session.commit()

    # Initially pending
    assert entry.status == "pending"
    assert entry.is_pending is True

    # Update to success
    entry.status = "success"
    session.commit()

    # Verify update
    retrieved = session.query(Entry).filter_by(id=entry.id).first()
    assert retrieved.status == "success"
    assert retrieved.is_successful is True


def test_multiple_entries_per_giveaway(session, giveaway):
    """Test that one giveaway can have multiple entry attempts"""
    # GIVEN: A giveaway exists in the database
    # WHEN: Creating multiple entries for the same giveaway (e.g., retry after failure)
    # THEN: All entries are stored and can be queried by giveaway_id

    entry1 = Entry(
        giveaway_id=giveaway.id,
        points_spent=50,
        entry_type="manual",
        status="failed",
        error_message="Network error",
    )
    entry2 = Entry(
        giveaway_id=giveaway.id,
        points_spent=50,
        entry_type="manual",
        status="success",
    )

    session.add_all([entry1, entry2])
    session.commit()

    # Both entries reference the same giveaway
    assert entry1.giveaway_id == giveaway.id
    assert entry2.giveaway_id == giveaway.id
    assert entry1.id != entry2.id

    # Verify we can query all entries for a giveaway
    entries = session.query(Entry).filter_by(giveaway_id=giveaway.id).all()
    assert len(entries) == 2


def test_computed_properties_readonly(session, giveaway):
    """Test that computed properties cannot be set directly"""
    # GIVEN: An entry exists in the database
    # WHEN: Attempting to set computed properties directly
    # THEN: AttributeError is raised for all read-only computed properties

    entry = Entry(
        giveaway_id=giveaway.id,
        points_spent=50,
        entry_type="manual",
        status="success",
    )
    session.add(entry)
    session.commit()

    # Verify is_successful cannot be set directly
    with pytest.raises(AttributeError):
        entry.is_successful = False

    # Verify is_failed cannot be set directly
    with pytest.raises(AttributeError):
        entry.is_failed = True

    # Verify is_pending cannot be set directly
    with pytest.raises(AttributeError):
        entry.is_pending = True


def test_entry_points_spent_tracking(session, giveaway):
    """Test tracking different point amounts"""
    # GIVEN: A giveaway exists in the database
    # WHEN: Creating entries with different point amounts (10, 100, 500)
    # THEN: Each entry correctly tracks its points_spent value

    entry1 = Entry(giveaway_id=giveaway.id, points_spent=10, entry_type="auto", status="success")
    entry2 = Entry(giveaway_id=giveaway.id, points_spent=100, entry_type="wishlist", status="success")
    entry3 = Entry(giveaway_id=giveaway.id, points_spent=500, entry_type="manual", status="success")

    session.add_all([entry1, entry2, entry3])
    session.commit()

    assert entry1.points_spent == 10
    assert entry2.points_spent == 100
    assert entry3.points_spent == 500


def test_entry_entered_at_default(session, giveaway):
    """Test that entered_at gets default value"""
    # GIVEN: A giveaway exists in the database
    # WHEN: Creating an entry without specifying entered_at
    # THEN: The entered_at field is automatically set to current time

    entry = Entry(
        giveaway_id=giveaway.id,
        points_spent=50,
        entry_type="manual",
        status="success",
    )
    session.add(entry)
    session.commit()

    assert entry.entered_at is not None
    assert isinstance(entry.entered_at, datetime)
