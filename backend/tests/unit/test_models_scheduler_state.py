"""Unit tests for SchedulerState model.

This module contains comprehensive tests for the SchedulerState model, including:
- Singleton pattern with id=1
- Timestamp and statistics tracking (total_scans, total_entries, total_errors)
- Timing fields (last_scan_at, next_scan_at)
- Computed properties (has_run, time_since_last_scan, time_until_next_scan)
- Lifecycle testing from initial state through multiple scans
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models.base import Base
from models.scheduler_state import SchedulerState


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


def test_scheduler_state_creation_with_defaults(session):
    """Test creating SchedulerState with default values"""
    # GIVEN: A database session is available
    # WHEN: Creating a scheduler state with only id specified
    # THEN: All counters default to 0 and timing fields to None

    state = SchedulerState(id=1)
    session.add(state)
    session.commit()

    assert state.id == 1
    assert state.last_scan_at is None
    assert state.next_scan_at is None
    assert state.total_scans == 0
    assert state.total_entries == 0
    assert state.total_errors == 0


def test_scheduler_state_singleton(session):
    """Test that SchedulerState is designed as a singleton (id=1)"""
    # GIVEN: A database session is available
    # WHEN: Creating and retrieving a scheduler state with id=1
    # THEN: The state can be retrieved and represents the singleton instance

    state = SchedulerState(id=1)
    session.add(state)
    session.commit()

    # Retrieve the state
    retrieved = session.query(SchedulerState).filter_by(id=1).first()
    assert retrieved is not None
    assert retrieved.id == 1


def test_scheduler_state_timestamps(session):
    """Test that timestamps are automatically created"""
    # GIVEN: A database session is available
    # WHEN: Creating and saving a new scheduler state
    # THEN: Timestamps (created_at, updated_at) are automatically set to the same value

    state = SchedulerState(id=1)
    session.add(state)
    session.commit()

    assert isinstance(state.created_at, datetime)
    assert isinstance(state.updated_at, datetime)
    assert state.created_at == state.updated_at


def test_scheduler_state_repr(session):
    """Test string representation of SchedulerState"""
    # GIVEN: A scheduler state with 10 scans and 50 entries exists
    # WHEN: Getting the string representation of the state
    # THEN: The repr includes id, scans, and entries counts

    state = SchedulerState(id=1, total_scans=10, total_entries=50)
    session.add(state)
    session.commit()

    repr_str = repr(state)
    assert "SchedulerState" in repr_str
    assert "id=1" in repr_str
    assert "scans=10" in repr_str
    assert "entries=50" in repr_str


def test_scheduler_state_timing_fields(session):
    """Test last_scan_at and next_scan_at fields"""
    # GIVEN: A database session is available
    # WHEN: Creating a scheduler state with last_scan and next_scan times
    # THEN: Both timing fields are correctly stored

    last_scan = datetime.utcnow() - timedelta(hours=1)
    next_scan = datetime.utcnow() + timedelta(hours=1)

    state = SchedulerState(
        id=1,
        last_scan_at=last_scan,
        next_scan_at=next_scan,
    )
    session.add(state)
    session.commit()

    assert state.last_scan_at == last_scan
    assert state.next_scan_at == next_scan


def test_scheduler_state_statistics(session):
    """Test statistics/counter fields"""
    # GIVEN: A database session is available
    # WHEN: Creating a scheduler state with statistics (scans, entries, errors)
    # THEN: All counter fields are correctly stored

    state = SchedulerState(
        id=1,
        total_scans=100,
        total_entries=500,
        total_errors=5,
    )
    session.add(state)
    session.commit()

    assert state.total_scans == 100
    assert state.total_entries == 500
    assert state.total_errors == 5


def test_has_run_property_never_ran(session):
    """Test has_run property when scheduler never ran"""
    # GIVEN: A scheduler state that has never run (last_scan_at is None)
    # WHEN: Checking the has_run property
    # THEN: The property returns False

    state = SchedulerState(id=1)
    session.add(state)
    session.commit()

    assert state.has_run is False


def test_has_run_property_has_ran(session):
    """Test has_run property when scheduler has run before"""
    # GIVEN: A scheduler state that has run before (last_scan_at is set)
    # WHEN: Checking the has_run property
    # THEN: The property returns True

    state = SchedulerState(
        id=1,
        last_scan_at=datetime.utcnow() - timedelta(hours=1),
    )
    session.add(state)
    session.commit()

    assert state.has_run is True


def test_time_since_last_scan_property(session):
    """Test time_since_last_scan calculation"""
    # GIVEN: A scheduler state that last ran 2 hours ago
    # WHEN: Accessing the time_since_last_scan property
    # THEN: The property returns approximately 7200 seconds

    # Set last scan to 2 hours ago
    last_scan = datetime.utcnow() - timedelta(hours=2)
    state = SchedulerState(id=1, last_scan_at=last_scan)
    session.add(state)
    session.commit()

    time_since = state.time_since_last_scan
    assert time_since is not None
    # Should be approximately 2 hours (7200 seconds), with small tolerance
    assert 7100 < time_since < 7300


def test_time_since_last_scan_never_ran(session):
    """Test time_since_last_scan when never ran"""
    # GIVEN: A scheduler state that has never run
    # WHEN: Accessing the time_since_last_scan property
    # THEN: The property returns None

    state = SchedulerState(id=1)
    session.add(state)
    session.commit()

    assert state.time_since_last_scan is None


def test_time_until_next_scan_property(session):
    """Test time_until_next_scan calculation"""
    # GIVEN: A scheduler state with next scan scheduled in 1 hour
    # WHEN: Accessing the time_until_next_scan property
    # THEN: The property returns approximately 3600 seconds

    # Set next scan to 1 hour from now
    next_scan = datetime.utcnow() + timedelta(hours=1)
    state = SchedulerState(id=1, next_scan_at=next_scan)
    session.add(state)
    session.commit()

    time_until = state.time_until_next_scan
    assert time_until is not None
    # Should be approximately 1 hour (3600 seconds), with small tolerance
    assert 3500 < time_until < 3700


def test_time_until_next_scan_not_scheduled(session):
    """Test time_until_next_scan when not scheduled"""
    # GIVEN: A scheduler state with no next scan scheduled
    # WHEN: Accessing the time_until_next_scan property
    # THEN: The property returns None

    state = SchedulerState(id=1)
    session.add(state)
    session.commit()

    assert state.time_until_next_scan is None


def test_time_until_next_scan_negative(session):
    """Test time_until_next_scan doesn't return negative values"""
    # GIVEN: A scheduler state with next_scan_at in the past (overdue)
    # WHEN: Accessing the time_until_next_scan property
    # THEN: The property returns 0 instead of a negative value

    # Set next scan to the past
    past_scan = datetime.utcnow() - timedelta(hours=1)
    state = SchedulerState(id=1, next_scan_at=past_scan)
    session.add(state)
    session.commit()

    # Should return 0, not negative
    assert state.time_until_next_scan == 0


def test_update_statistics(session):
    """Test updating statistics counters"""
    # GIVEN: A scheduler state with existing statistics exists
    # WHEN: Incrementing the statistics counters
    # THEN: All updates are persisted correctly

    state = SchedulerState(id=1, total_scans=10, total_entries=50, total_errors=2)
    session.add(state)
    session.commit()

    # Simulate a scan completing
    state.total_scans += 1
    state.total_entries += 5
    state.total_errors += 1
    session.commit()

    # Verify updates
    retrieved = session.query(SchedulerState).filter_by(id=1).first()
    assert retrieved.total_scans == 11
    assert retrieved.total_entries == 55
    assert retrieved.total_errors == 3


def test_update_timing(session):
    """Test updating timing information"""
    # GIVEN: A scheduler state that has never run exists
    # WHEN: Updating timing fields after first scan completes
    # THEN: The timing fields are updated and has_run becomes True

    state = SchedulerState(id=1)
    session.add(state)
    session.commit()

    # Initially no scans
    assert state.last_scan_at is None
    assert state.has_run is False

    # Update after first scan
    now = datetime.utcnow()
    next_scan = now + timedelta(minutes=30)
    state.last_scan_at = now
    state.next_scan_at = next_scan
    session.commit()

    # Verify updates
    retrieved = session.query(SchedulerState).filter_by(id=1).first()
    assert retrieved.has_run is True
    assert retrieved.last_scan_at == now
    assert retrieved.next_scan_at == next_scan


def test_computed_properties_readonly(session):
    """Test that computed properties cannot be set directly"""
    # GIVEN: A scheduler state exists in the database
    # WHEN: Attempting to set computed properties directly
    # THEN: AttributeError is raised for all read-only computed properties

    state = SchedulerState(id=1)
    session.add(state)
    session.commit()

    # Verify has_run cannot be set directly
    with pytest.raises(AttributeError):
        state.has_run = True

    # Verify time_since_last_scan cannot be set directly
    with pytest.raises(AttributeError):
        state.time_since_last_scan = 100

    # Verify time_until_next_scan cannot be set directly
    with pytest.raises(AttributeError):
        state.time_until_next_scan = 100


def test_nullable_fields(session):
    """Test that optional fields can be None"""
    # GIVEN: A database session is available
    # WHEN: Creating a scheduler state with only id specified
    # THEN: Optional timing fields default to None

    state = SchedulerState(id=1)
    session.add(state)
    session.commit()

    assert state.last_scan_at is None
    assert state.next_scan_at is None


def test_scheduler_state_complete_lifecycle(session):
    """Test complete lifecycle of scheduler state"""
    # GIVEN: A new scheduler state is created
    # WHEN: Simulating multiple scans and errors over time
    # THEN: All state transitions and statistics are tracked correctly

    # Initial state
    state = SchedulerState(id=1)
    session.add(state)
    session.commit()

    assert state.has_run is False
    assert state.total_scans == 0

    # First scan completes
    state.last_scan_at = datetime.utcnow()
    state.next_scan_at = datetime.utcnow() + timedelta(minutes=30)
    state.total_scans = 1
    state.total_entries = 3
    session.commit()

    assert state.has_run is True
    assert state.total_scans == 1
    assert state.time_since_last_scan is not None
    assert state.time_until_next_scan is not None

    # Error occurs
    state.total_errors += 1
    session.commit()

    assert state.total_errors == 1

    # Multiple scans complete
    for _ in range(5):
        state.total_scans += 1
        state.total_entries += 2
        state.last_scan_at = datetime.utcnow()

    session.commit()

    assert state.total_scans == 6
    assert state.total_entries == 13
