"""Unit tests for system API router."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from api.routers.system import (
    health_check,
    system_info,
    get_logs,
)
from models.activity_log import ActivityLog


def create_mock_activity_log(log_id: int, level: str, event_type: str, message: str):
    """Create a mock ActivityLog object."""
    log = MagicMock(spec=ActivityLog)
    log.id = log_id
    log.level = level
    log.event_type = event_type
    log.message = message
    log.created_at = datetime.utcnow()
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


@pytest.mark.asyncio
async def test_get_logs():
    """Test GET /system/logs endpoint."""
    mock_service = AsyncMock()
    mock_logs = [
        create_mock_activity_log(1, "info", "scan", "Test log 1"),
        create_mock_activity_log(2, "warning", "entry", "Test log 2"),
    ]
    mock_service.get_recent_logs.return_value = mock_logs

    result = await get_logs(notification_service=mock_service, limit=50, level=None, event_type=None)

    assert result["success"] is True
    assert "data" in result
    assert result["data"]["count"] == 2
    assert result["data"]["limit"] == 50
    assert len(result["data"]["logs"]) == 2
    mock_service.get_recent_logs.assert_called_once_with(limit=50)


@pytest.mark.asyncio
async def test_get_logs_with_level_filter():
    """Test GET /system/logs with level filter."""
    mock_service = AsyncMock()
    mock_logs = [
        create_mock_activity_log(1, "error", "error", "Error message"),
    ]
    mock_service.get_logs_by_level.return_value = mock_logs

    result = await get_logs(notification_service=mock_service, limit=50, level="error", event_type=None)

    assert result["success"] is True
    assert result["data"]["count"] == 1
    mock_service.get_logs_by_level.assert_called_once_with(
        level="error",
        limit=50,
    )


@pytest.mark.asyncio
async def test_get_logs_with_custom_limit():
    """Test GET /system/logs with custom limit."""
    mock_service = AsyncMock()
    mock_logs = []
    mock_service.get_recent_logs.return_value = mock_logs

    result = await get_logs(notification_service=mock_service, limit=100, level=None, event_type=None)

    assert result["success"] is True
    assert result["data"]["limit"] == 100
    mock_service.get_recent_logs.assert_called_once_with(limit=100)


@pytest.mark.asyncio
async def test_get_logs_empty_result():
    """Test GET /system/logs with no logs."""
    mock_service = AsyncMock()
    mock_service.get_recent_logs.return_value = []

    result = await get_logs(notification_service=mock_service, limit=50, level=None, event_type=None)

    assert result["success"] is True
    assert result["data"]["count"] == 0
    assert result["data"]["logs"] == []


@pytest.mark.asyncio
async def test_get_logs_formats_correctly():
    """Test GET /system/logs formats log data correctly."""
    mock_service = AsyncMock()
    mock_log = create_mock_activity_log(123, "info", "entry", "Test message")
    mock_service.get_recent_logs.return_value = [mock_log]

    result = await get_logs(notification_service=mock_service, limit=50, level=None, event_type=None)

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
    mock_service.get_recent_logs.return_value = [mock_log]

    result = await get_logs(notification_service=mock_service, limit=50, level=None, event_type=None)

    log = result["data"]["logs"][0]
    assert log["created_at"] is None
