"""Unit tests for system API router."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.routers.system import (
    get_logs,
    health_check,
    system_info,
)
from core.time import utcnow
from models.activity_log import ActivityLog


def create_mock_activity_log(log_id: int, level: str, event_type: str, message: str):
    """Create a mock ActivityLog object."""
    log = MagicMock(spec=ActivityLog)
    log.id = log_id
    log.level = level
    log.event_type = event_type
    log.message = message
    log.created_at = utcnow()
    return log


@pytest.mark.asyncio
async def test_health_check():
    """Test GET /system/health endpoint."""
    result = await health_check()

    assert result["success"] is True
    assert "data" in result
    assert result["data"]["status"] == "healthy"
    assert "timestamp" in result["data"]
    assert result["data"]["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_health_check_returns_timestamp():
    """Test health check includes valid timestamp."""
    result = await health_check()

    # Verify timestamp is in ISO format
    timestamp = result["data"]["timestamp"]
    assert isinstance(timestamp, str)
    # Should be parseable as datetime
    datetime.fromisoformat(timestamp)


@pytest.mark.asyncio
async def test_system_info():
    """Test GET /system/info endpoint."""
    result = await system_info()

    assert result["success"] is True
    assert "data" in result
    assert result["data"]["app_name"] == "SteamSelfGifter"
    assert result["data"]["version"] == "0.1.0"
    assert "debug_mode" in result["data"]
    assert "database_url" in result["data"]


@pytest.mark.asyncio
async def test_system_info_includes_config():
    """Test system info includes configuration details."""
    result = await system_info()

    data = result["data"]
    # Should have debug mode (boolean)
    assert isinstance(data["debug_mode"], bool)
    # Should have database URL (string)
    assert isinstance(data["database_url"], str)


def _call_get_logs(mock_service, **overrides):
    kwargs = dict(
        notification_service=mock_service,
        limit=50,
        offset=0,
        level=None,
        event_type=None,
        search=None,
        from_date=None,
        to_date=None,
    )
    kwargs.update(overrides)
    return get_logs(**kwargs)


@pytest.mark.asyncio
async def test_get_logs():
    """Test GET /system/logs endpoint."""
    mock_service = AsyncMock()
    mock_logs = [
        create_mock_activity_log(1, "info", "scan", "Test log 1"),
        create_mock_activity_log(2, "warning", "entry", "Test log 2"),
    ]
    mock_service.search_logs.return_value = (mock_logs, 2)

    result = await _call_get_logs(mock_service)

    assert result["success"] is True
    assert "data" in result
    assert result["data"]["count"] == 2
    assert result["data"]["limit"] == 50
    assert len(result["data"]["logs"]) == 2


@pytest.mark.asyncio
async def test_get_logs_combinable_filters():
    """Level, event type, search and dates are all forwarded together."""
    from datetime import date, time, timedelta

    mock_service = AsyncMock()
    mock_service.search_logs.return_value = ([], 0)

    result = await _call_get_logs(
        mock_service,
        level="error",
        event_type="scan",
        search="drift",
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 15),
        offset=100,
    )

    assert result["success"] is True
    call = mock_service.search_logs.call_args.kwargs
    assert call["level"] == "error"
    assert call["event_type"] == "scan"
    assert call["search"] == "drift"
    assert call["from_date"] == datetime.combine(date(2026, 7, 1), time.min)
    assert call["to_date"] == datetime.combine(date(2026, 7, 15) + timedelta(days=1), time.min)
    assert call["offset"] == 100


@pytest.mark.asyncio
async def test_get_logs_count_is_total_not_page_size():
    """The count field reports total matching rows for pagination."""
    mock_service = AsyncMock()
    mock_log = create_mock_activity_log(1, "info", "scan", "Test")
    mock_service.search_logs.return_value = ([mock_log], 412)

    result = await _call_get_logs(mock_service, limit=1)

    assert result["data"]["count"] == 412
    assert len(result["data"]["logs"]) == 1


@pytest.mark.asyncio
async def test_get_logs_empty_result():
    """Test GET /system/logs with no logs."""
    mock_service = AsyncMock()
    mock_service.search_logs.return_value = ([], 0)

    result = await _call_get_logs(mock_service)

    assert result["success"] is True
    assert result["data"]["count"] == 0
    assert result["data"]["logs"] == []


@pytest.mark.asyncio
async def test_get_logs_formats_correctly():
    """Test GET /system/logs formats log data correctly."""
    mock_service = AsyncMock()
    mock_log = create_mock_activity_log(123, "info", "entry", "Test message")
    mock_service.search_logs.return_value = ([mock_log], 1)

    result = await _call_get_logs(mock_service)

    log = result["data"]["logs"][0]
    assert log["id"] == 123
    assert log["level"] == "info"
    assert log["event_type"] == "entry"
    assert log["message"] == "Test message"
    assert "created_at" in log
    # Timestamp should be in ISO format
    datetime.fromisoformat(log["created_at"])


@pytest.mark.asyncio
async def test_get_logs_handles_null_created_at():
    """Test GET /system/logs handles null created_at."""
    mock_service = AsyncMock()
    mock_log = create_mock_activity_log(1, "info", "scan", "Test")
    mock_log.created_at = None
    mock_service.search_logs.return_value = ([mock_log], 1)

    result = await _call_get_logs(mock_service)

    log = result["data"]["logs"][0]
    assert log["created_at"] is None
