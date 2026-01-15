"""Unit tests for ActivityLog model.

This module contains comprehensive tests for the ActivityLog model, including:
- Basic creation with minimal and complete fields
- Automatic timestamp handling
- Different log levels (info, warning, error) and event types (scan, entry, error, config)
- Computed properties (is_info, is_warning, is_error)
- JSON details field for structured logging
- Filtering and chronological ordering
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models.base import Base
from models.activity_log import ActivityLog


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


def test_activity_log_creation_minimal(session):
    """Test creating ActivityLog with required fields only"""
    # GIVEN: A database session is available
    # WHEN: Creating a log with only required fields (level, event_type, message)
    # THEN: The log is created with details as None and created_at auto-set

    log = ActivityLog(
        level="info",
        event_type="scan",
        message="Scan completed successfully",
    )
    session.add(log)
    session.commit()

    assert log.id is not None
    assert log.level == "info"
    assert log.event_type == "scan"
    assert log.message == "Scan completed successfully"
    assert log.details is None
    assert isinstance(log.created_at, datetime)


def test_activity_log_creation_complete(session):
    """Test creating ActivityLog with all fields populated"""
    # GIVEN: A database session is available
    # WHEN: Creating a log with all fields including JSON details
    # THEN: All fields are correctly stored

    log = ActivityLog(
        level="error",
        event_type="entry",
        message="Failed to enter giveaway",
        details='{"giveaway_id": 123, "error": "Insufficient points"}',
    )
    session.add(log)
    session.commit()

    assert log.level == "error"
    assert log.event_type == "entry"
    assert log.message == "Failed to enter giveaway"
    assert log.details == '{"giveaway_id": 123, "error": "Insufficient points"}'


def test_activity_log_created_at(session):
    """Test that created_at is automatically set"""
    # GIVEN: A database session is available
    # WHEN: Creating and saving a new log entry
    # THEN: The created_at timestamp is automatically set to current time

    log = ActivityLog(
        level="info",
        event_type="scan",
        message="Test message",
    )
    session.add(log)
    session.commit()

    assert log.created_at is not None
    assert isinstance(log.created_at, datetime)


def test_activity_log_repr(session):
    """Test string representation of ActivityLog"""
    # GIVEN: An activity log exists in the database
    # WHEN: Getting the string representation of the log
    # THEN: The repr includes id, level, and event_type

    log = ActivityLog(
        level="warning",
        event_type="config",
        message="Configuration updated",
    )
    session.add(log)
    session.commit()

    repr_str = repr(log)
    assert "ActivityLog" in repr_str
    assert str(log.id) in repr_str
    assert "warning" in repr_str
    assert "config" in repr_str


def test_activity_log_levels(session):
    """Test different log levels"""
    # GIVEN: A database session is available
    # WHEN: Creating logs with different levels (info, warning, error)
    # THEN: Each log level is correctly stored

    log_info = ActivityLog(level="info", event_type="scan", message="Info message")
    log_warning = ActivityLog(level="warning", event_type="scan", message="Warning message")
    log_error = ActivityLog(level="error", event_type="scan", message="Error message")

    session.add_all([log_info, log_warning, log_error])
    session.commit()

    assert log_info.level == "info"
    assert log_warning.level == "warning"
    assert log_error.level == "error"


def test_activity_log_event_types(session):
    """Test different event types"""
    # GIVEN: A database session is available
    # WHEN: Creating logs with different event types (scan, entry, error, config)
    # THEN: Each event type is correctly stored

    log_scan = ActivityLog(level="info", event_type="scan", message="Scan event")
    log_entry = ActivityLog(level="info", event_type="entry", message="Entry event")
    log_error = ActivityLog(level="error", event_type="error", message="Error event")
    log_config = ActivityLog(level="info", event_type="config", message="Config event")

    session.add_all([log_scan, log_entry, log_error, log_config])
    session.commit()

    assert log_scan.event_type == "scan"
    assert log_entry.event_type == "entry"
    assert log_error.event_type == "error"
    assert log_config.event_type == "config"


def test_is_info_property(session):
    """Test is_info property"""
    # GIVEN: Logs with different levels exist
    # WHEN: Checking the is_info property
    # THEN: It returns True only for logs with level "info"

    log_info = ActivityLog(level="info", event_type="scan", message="Info")
    log_warning = ActivityLog(level="warning", event_type="scan", message="Warning")

    session.add_all([log_info, log_warning])
    session.commit()

    assert log_info.is_info is True
    assert log_warning.is_info is False


def test_is_warning_property(session):
    """Test is_warning property"""
    # GIVEN: Logs with different levels exist
    # WHEN: Checking the is_warning property
    # THEN: It returns True only for logs with level "warning"

    log_info = ActivityLog(level="info", event_type="scan", message="Info")
    log_warning = ActivityLog(level="warning", event_type="scan", message="Warning")

    session.add_all([log_info, log_warning])
    session.commit()

    assert log_info.is_warning is False
    assert log_warning.is_warning is True


def test_is_error_property(session):
    """Test is_error property"""
    # GIVEN: Logs with different levels exist
    # WHEN: Checking the is_error property
    # THEN: It returns True only for logs with level "error"

    log_info = ActivityLog(level="info", event_type="scan", message="Info")
    log_error = ActivityLog(level="error", event_type="scan", message="Error")

    session.add_all([log_info, log_error])
    session.commit()

    assert log_info.is_error is False
    assert log_error.is_error is True


def test_activity_log_with_details(session):
    """Test activity log with JSON details"""
    # GIVEN: A database session is available
    # WHEN: Creating a log with JSON details field
    # THEN: The JSON details are correctly stored

    details_json = '{"scan_id": 123, "giveaways_found": 50, "entries_made": 5}'
    log = ActivityLog(
        level="info",
        event_type="scan",
        message="Scan completed",
        details=details_json,
    )
    session.add(log)
    session.commit()

    assert log.details == details_json


def test_activity_log_nullable_details(session):
    """Test that details field is nullable"""
    # GIVEN: A database session is available
    # WHEN: Creating a log without details field
    # THEN: The details field defaults to None

    log = ActivityLog(
        level="info",
        event_type="scan",
        message="Simple log without details",
    )
    session.add(log)
    session.commit()

    assert log.details is None


def test_multiple_activity_logs(session):
    """Test creating multiple activity logs"""
    # GIVEN: A database session is available
    # WHEN: Creating multiple logs with different levels and event types
    # THEN: All logs are successfully created and stored

    logs = [
        ActivityLog(level="info", event_type="scan", message="Scan 1"),
        ActivityLog(level="info", event_type="scan", message="Scan 2"),
        ActivityLog(level="warning", event_type="entry", message="Entry warning"),
        ActivityLog(level="error", event_type="error", message="Error occurred"),
    ]

    session.add_all(logs)
    session.commit()

    # Verify all logs were created
    all_logs = session.query(ActivityLog).all()
    assert len(all_logs) == 4


def test_computed_properties_readonly(session):
    """Test that computed properties cannot be set directly"""
    # GIVEN: An activity log exists in the database
    # WHEN: Attempting to set computed properties directly
    # THEN: AttributeError is raised for all read-only computed properties

    log = ActivityLog(
        level="info",
        event_type="scan",
        message="Test",
    )
    session.add(log)
    session.commit()

    # Verify is_info cannot be set directly
    with pytest.raises(AttributeError):
        log.is_info = False

    # Verify is_warning cannot be set directly
    with pytest.raises(AttributeError):
        log.is_warning = True

    # Verify is_error cannot be set directly
    with pytest.raises(AttributeError):
        log.is_error = True


def test_activity_log_chronological_order(session):
    """Test that logs can be ordered chronologically"""
    # GIVEN: Multiple logs are created in sequence
    # WHEN: Querying logs ordered by created_at
    # THEN: Logs are returned in chronological order

    # Create logs in sequence
    log1 = ActivityLog(level="info", event_type="scan", message="First")
    session.add(log1)
    session.commit()

    log2 = ActivityLog(level="info", event_type="scan", message="Second")
    session.add(log2)
    session.commit()

    log3 = ActivityLog(level="info", event_type="scan", message="Third")
    session.add(log3)
    session.commit()

    # Query in chronological order
    logs = session.query(ActivityLog).order_by(ActivityLog.created_at).all()

    assert len(logs) == 3
    assert logs[0].message == "First"
    assert logs[1].message == "Second"
    assert logs[2].message == "Third"
    assert logs[0].created_at <= logs[1].created_at <= logs[2].created_at


def test_activity_log_filter_by_level(session):
    """Test filtering logs by level"""
    # GIVEN: Multiple logs with different levels exist
    # WHEN: Filtering logs by specific level
    # THEN: Only logs with that level are returned

    logs = [
        ActivityLog(level="info", event_type="scan", message="Info 1"),
        ActivityLog(level="info", event_type="scan", message="Info 2"),
        ActivityLog(level="error", event_type="error", message="Error 1"),
        ActivityLog(level="warning", event_type="scan", message="Warning 1"),
    ]
    session.add_all(logs)
    session.commit()

    # Filter for errors only
    errors = session.query(ActivityLog).filter_by(level="error").all()
    assert len(errors) == 1
    assert errors[0].is_error is True

    # Filter for info only
    infos = session.query(ActivityLog).filter_by(level="info").all()
    assert len(infos) == 2


def test_activity_log_filter_by_event_type(session):
    """Test filtering logs by event type"""
    # GIVEN: Multiple logs with different event types exist
    # WHEN: Filtering logs by specific event type
    # THEN: Only logs with that event type are returned

    logs = [
        ActivityLog(level="info", event_type="scan", message="Scan 1"),
        ActivityLog(level="info", event_type="scan", message="Scan 2"),
        ActivityLog(level="info", event_type="entry", message="Entry 1"),
        ActivityLog(level="error", event_type="error", message="Error 1"),
    ]
    session.add_all(logs)
    session.commit()

    # Filter for scan events
    scans = session.query(ActivityLog).filter_by(event_type="scan").all()
    assert len(scans) == 2

    # Filter for entry events
    entries = session.query(ActivityLog).filter_by(event_type="entry").all()
    assert len(entries) == 1


def test_activity_log_long_message(session):
    """Test activity log with long message"""
    # GIVEN: A database session is available
    # WHEN: Creating a log with a very long message (1000 characters)
    # THEN: The long message is correctly stored without truncation

    long_message = "A" * 1000  # 1000 character message
    log = ActivityLog(
        level="info",
        event_type="scan",
        message=long_message,
    )
    session.add(log)
    session.commit()

    assert log.message == long_message
    assert len(log.message) == 1000
