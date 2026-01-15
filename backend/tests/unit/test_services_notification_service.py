"""Unit tests for NotificationService."""

import pytest
import json
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from models.base import Base
from services.notification_service import NotificationService


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


@pytest.mark.asyncio
async def test_notification_service_init(test_db):
    """Test NotificationService initialization."""
    async with test_db() as session:
        service = NotificationService(session)

        assert service.session == session
        assert service.repo is not None


@pytest.mark.asyncio
async def test_log_activity_info(test_db):
    """Test logging info-level activity."""
    async with test_db() as session:
        service = NotificationService(session)

        log = await service.log_activity(
            level="info",
            event_type="scan",
            message="Found 15 new giveaways",
            details={"count": 15, "page": 1}
        )

        assert log is not None
        assert log.level == "info"
        assert log.event_type == "scan"
        assert log.message == "Found 15 new giveaways"
        assert log.details is not None

        # Verify details JSON
        details = json.loads(log.details)
        assert details["count"] == 15
        assert details["page"] == 1


@pytest.mark.asyncio
async def test_log_activity_no_details(test_db):
    """Test logging activity without details."""
    async with test_db() as session:
        service = NotificationService(session)

        log = await service.log_activity(
            level="info",
            event_type="config",
            message="Settings updated"
        )

        assert log.details is None


@pytest.mark.asyncio
async def test_log_activity_invalid_level(test_db):
    """Test logging with invalid level raises error."""
    async with test_db() as session:
        service = NotificationService(session)

        with pytest.raises(ValueError, match="Invalid log level"):
            await service.log_activity(
                level="invalid",
                event_type="scan",
                message="Test"
            )


@pytest.mark.asyncio
async def test_broadcast_event(test_db):
    """Test preparing event for broadcasting."""
    async with test_db() as session:
        service = NotificationService(session)

        event = await service.broadcast_event(
            event_type="scan_complete",
            data={"new": 5, "updated": 3}
        )

        assert event["type"] == "scan_complete"
        assert event["data"]["new"] == 5
        assert event["data"]["updated"] == 3
        assert "timestamp" in event


@pytest.mark.asyncio
async def test_broadcast_event_with_logging(test_db):
    """Test broadcasting event also logs to database."""
    async with test_db() as session:
        service = NotificationService(session)

        event = await service.broadcast_event(
            event_type="entry_success",
            data={"game": "Portal 2", "points": 50},
            log_activity=True,
            log_level="info",
            log_message="Successfully entered Portal 2"
        )

        assert event["type"] == "entry_success"

        # Verify it was also logged
        logs = await service.get_recent_logs(limit=1)
        assert len(logs) == 1
        assert logs[0].message == "Successfully entered Portal 2"
        assert logs[0].level == "info"


@pytest.mark.asyncio
async def test_get_recent_logs(test_db):
    """Test getting recent logs."""
    async with test_db() as session:
        service = NotificationService(session)

        # Create multiple logs
        await service.log_activity("info", "scan", "Log 1")
        await service.log_activity("warning", "entry", "Log 2")
        await service.log_activity("error", "error", "Log 3")

        logs = await service.get_recent_logs(limit=10)

        assert len(logs) == 3
        # Should be in reverse chronological order (newest first)
        assert logs[0].message == "Log 3"
        assert logs[1].message == "Log 2"
        assert logs[2].message == "Log 1"


@pytest.mark.asyncio
async def test_get_recent_logs_with_limit(test_db):
    """Test getting recent logs respects limit."""
    async with test_db() as session:
        service = NotificationService(session)

        # Create 5 logs
        for i in range(5):
            await service.log_activity("info", "scan", f"Log {i}")

        logs = await service.get_recent_logs(limit=3)

        assert len(logs) == 3


@pytest.mark.asyncio
async def test_get_logs_by_level(test_db):
    """Test filtering logs by level."""
    async with test_db() as session:
        service = NotificationService(session)

        await service.log_activity("info", "scan", "Info log")
        await service.log_activity("error", "error", "Error log")
        await service.log_activity("warning", "entry", "Warning log")
        await service.log_activity("error", "error", "Another error")

        errors = await service.get_logs_by_level("error")

        assert len(errors) == 2
        assert all(log.level == "error" for log in errors)


@pytest.mark.asyncio
async def test_get_logs_by_event_type(test_db):
    """Test filtering logs by event type."""
    async with test_db() as session:
        service = NotificationService(session)

        await service.log_activity("info", "scan", "Scan 1")
        await service.log_activity("info", "entry", "Entry 1")
        await service.log_activity("info", "scan", "Scan 2")

        scan_logs = await service.get_logs_by_event_type("scan")

        assert len(scan_logs) == 2
        assert all(log.event_type == "scan" for log in scan_logs)


@pytest.mark.asyncio
async def test_get_error_count(test_db):
    """Test counting error logs."""
    async with test_db() as session:
        service = NotificationService(session)

        await service.log_activity("info", "scan", "Info")
        await service.log_activity("error", "error", "Error 1")
        await service.log_activity("error", "error", "Error 2")

        error_count = await service.get_error_count()

        assert error_count == 2


@pytest.mark.asyncio
async def test_get_warning_count(test_db):
    """Test counting warning logs."""
    async with test_db() as session:
        service = NotificationService(session)

        await service.log_activity("info", "scan", "Info")
        await service.log_activity("warning", "entry", "Warning 1")
        await service.log_activity("warning", "entry", "Warning 2")
        await service.log_activity("warning", "entry", "Warning 3")

        warning_count = await service.get_warning_count()

        assert warning_count == 3


@pytest.mark.asyncio
async def test_log_scan_start(test_db):
    """Test convenience method for logging scan start."""
    async with test_db() as session:
        service = NotificationService(session)

        log = await service.log_scan_start(pages=3)

        assert log.level == "info"
        assert log.event_type == "scan"
        assert "3 pages" in log.message

        details = json.loads(log.details)
        assert details["pages"] == 3


@pytest.mark.asyncio
async def test_log_scan_complete(test_db):
    """Test convenience method for logging scan completion."""
    async with test_db() as session:
        service = NotificationService(session)

        log = await service.log_scan_complete(new_count=5, updated_count=3)

        assert log.level == "info"
        assert log.event_type == "scan"
        assert "5 new" in log.message
        assert "3 updated" in log.message

        details = json.loads(log.details)
        assert details["new"] == 5
        assert details["updated"] == 3


@pytest.mark.asyncio
async def test_log_entry_success(test_db):
    """Test convenience method for logging successful entry."""
    async with test_db() as session:
        service = NotificationService(session)

        log = await service.log_entry_success(
            giveaway_code="AbCd1",
            game_name="Portal 2",
            points=50
        )

        assert log.level == "info"
        assert log.event_type == "entry"
        assert "Portal 2" in log.message
        assert "50P" in log.message

        details = json.loads(log.details)
        assert details["code"] == "AbCd1"
        assert details["game"] == "Portal 2"
        assert details["points"] == 50


@pytest.mark.asyncio
async def test_log_entry_failure(test_db):
    """Test convenience method for logging failed entry."""
    async with test_db() as session:
        service = NotificationService(session)

        log = await service.log_entry_failure(
            giveaway_code="AbCd1",
            game_name="Portal 2",
            reason="Insufficient points"
        )

        assert log.level == "warning"
        assert log.event_type == "entry"
        assert "Portal 2" in log.message
        assert "Insufficient points" in log.message

        details = json.loads(log.details)
        assert details["code"] == "AbCd1"
        assert details["reason"] == "Insufficient points"


@pytest.mark.asyncio
async def test_log_error(test_db):
    """Test convenience method for logging errors."""
    async with test_db() as session:
        service = NotificationService(session)

        log = await service.log_error(
            error_type="api",
            message="SteamGifts API timeout",
            details={"url": "https://steamgifts.com/api"}
        )

        assert log.level == "error"
        assert log.event_type == "error"
        assert "[api]" in log.message
        assert "timeout" in log.message

        details = json.loads(log.details)
        assert details["url"] == "https://steamgifts.com/api"


@pytest.mark.asyncio
async def test_log_error_no_details(test_db):
    """Test logging error without details."""
    async with test_db() as session:
        service = NotificationService(session)

        log = await service.log_error(
            error_type="system",
            message="Unknown error"
        )

        assert log.level == "error"
        assert log.details is None


@pytest.mark.asyncio
async def test_multiple_operations(test_db):
    """Test multiple logging operations in sequence."""
    async with test_db() as session:
        service = NotificationService(session)

        # Log various activities
        await service.log_scan_start(pages=3)
        await service.log_entry_success("GA1", "Game 1", 50)
        await service.log_entry_success("GA2", "Game 2", 75)
        await service.log_entry_failure("GA3", "Game 3", "Already entered")
        await service.log_scan_complete(new_count=10, updated_count=5)

        # Verify all logs
        all_logs = await service.get_recent_logs(limit=100)
        assert len(all_logs) == 5

        # Check specific log types
        entry_logs = await service.get_logs_by_event_type("entry")
        assert len(entry_logs) == 3

        scan_logs = await service.get_logs_by_event_type("scan")
        assert len(scan_logs) == 2


@pytest.mark.asyncio
async def test_broadcast_event_default_log_message(test_db):
    """Test broadcasting event with default log message."""
    async with test_db() as session:
        service = NotificationService(session)

        event = await service.broadcast_event(
            event_type="config_change",
            data={"setting": "autojoin", "value": True},
            log_activity=True
        )

        # Verify event structure
        assert event["type"] == "config_change"

        # Verify default log message
        logs = await service.get_recent_logs(limit=1)
        assert "Event: config_change" in logs[0].message
