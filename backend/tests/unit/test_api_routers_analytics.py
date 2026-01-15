"""Unit tests for analytics API router."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, UTC

from api.routers.analytics import (
    get_analytics_overview,
    get_entry_summary,
    get_giveaway_summary,
    get_game_summary,
    get_scheduler_summary,
    get_points_analytics,
    get_recent_activity,
    get_dashboard_data,
)


def create_mock_entry(
    id=1,
    giveaway_id=123,
    points_spent=50,
    status="success",
    entered_at=None,
):
    """Create a mock entry object."""
    mock = MagicMock()
    mock.id = id
    mock.giveaway_id = giveaway_id
    mock.points_spent = points_spent
    mock.status = status
    mock.entered_at = entered_at or datetime.now(UTC)
    return mock


def create_mock_giveaway(
    code="TEST123",
    game_name="Test Game",
    price=50,
    end_time=None,
):
    """Create a mock giveaway object."""
    mock = MagicMock()
    mock.code = code
    mock.game_name = game_name
    mock.price = price
    mock.end_time = end_time or datetime.now(UTC)
    return mock


@pytest.mark.asyncio
async def test_get_analytics_overview():
    """Test GET /analytics/overview endpoint."""
    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.get_giveaway_stats.return_value = {
        "total": 100,
        "active": 75,
        "entered": 25,
        "hidden": 5,
    }
    mock_giveaway_service.get_entry_stats.return_value = {
        "total": 50,
        "successful": 45,
        "failed": 5,
        "success_rate": 90.0,
        "total_points_spent": 2500,
        "by_type": {"manual": 10, "auto": 35, "wishlist": 5},
    }

    result = await get_analytics_overview(giveaway_service=mock_giveaway_service)

    assert result["success"] is True
    assert result["data"]["giveaways"]["total"] == 100
    assert result["data"]["entries"]["total"] == 50
    assert result["data"]["entries"]["success_rate"] == 90.0


@pytest.mark.asyncio
async def test_get_entry_summary():
    """Test GET /analytics/entries/summary endpoint."""
    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.get_entry_stats.return_value = {
        "total": 100,
        "successful": 85,
        "failed": 15,
        "success_rate": 85.0,
        "total_points_spent": 4250,
        "by_type": {"manual": 25, "auto": 60, "wishlist": 15},
    }
    mock_giveaway_service.entry_repo.get_average_points_per_entry.return_value = 50.0

    result = await get_entry_summary(giveaway_service=mock_giveaway_service)

    assert result["success"] is True
    assert result["data"]["total_entries"] == 100
    # The endpoint calculates average from total_points_spent / total = 4250 / 100 = 42.5
    assert result["data"]["average_points_per_entry"] == 42.5


@pytest.mark.asyncio
async def test_get_giveaway_summary():
    """Test GET /analytics/giveaways/summary endpoint."""
    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.get_giveaway_stats.return_value = {
        "total": 100,
        "active": 75,
        "entered": 25,
        "hidden": 5,
    }
    mock_giveaway = create_mock_giveaway()
    mock_giveaway_service.get_expiring_soon.return_value = [mock_giveaway]

    result = await get_giveaway_summary(giveaway_service=mock_giveaway_service)

    assert result["success"] is True
    assert result["data"]["total_giveaways"] == 100
    assert result["data"]["expiring_24h"] == 1


@pytest.mark.asyncio
async def test_get_game_summary():
    """Test GET /analytics/games/summary endpoint."""
    mock_game_service = AsyncMock()
    mock_game_service.get_game_cache_stats.return_value = {
        "total": 500,
        "by_type": {"game": 450, "dlc": 40, "bundle": 10},
        "stale_count": 20,
    }

    result = await get_game_summary(game_service=mock_game_service)

    assert result["success"] is True
    assert result["data"]["total_games"] == 500
    assert result["data"]["stale_games"] == 20


@pytest.mark.asyncio
async def test_get_scheduler_summary():
    """Test GET /analytics/scheduler/summary endpoint."""
    mock_scheduler_service = AsyncMock()
    mock_scheduler_service.get_scheduler_stats.return_value = {
        "total_scans": 100,
        "total_entries": 500,
        "total_errors": 5,
        "last_scan_at": datetime.now(UTC),
        "next_scan_at": datetime.now(UTC),
    }

    result = await get_scheduler_summary(scheduler_service=mock_scheduler_service)

    assert result["success"] is True
    assert result["data"]["total_scans"] == 100
    assert result["data"]["total_errors"] == 5


@pytest.mark.asyncio
async def test_get_points_analytics():
    """Test GET /analytics/points endpoint."""
    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.entry_repo.get_total_points_spent.return_value = 5000
    mock_giveaway_service.entry_repo.get_total_points_by_status.side_effect = [4500, 500]
    mock_giveaway_service.entry_repo.get_average_points_per_entry.return_value = 50.0
    mock_giveaway_service.get_entry_stats.return_value = {
        "by_type": {"manual": 25, "auto": 60, "wishlist": 15},
    }

    result = await get_points_analytics(giveaway_service=mock_giveaway_service)

    assert result["success"] is True
    assert result["data"]["total_points_spent"] == 5000
    assert result["data"]["average_points_per_entry"] == 50.0


@pytest.mark.asyncio
async def test_get_recent_activity():
    """Test GET /analytics/recent-activity endpoint."""
    mock_giveaway_service = AsyncMock()
    mock_entry_success = create_mock_entry(status="success", points_spent=50)
    mock_entry_failed = create_mock_entry(status="failed", points_spent=0)
    mock_giveaway_service.entry_repo.get_entries_since.return_value = [
        mock_entry_success,
        mock_entry_failed,
    ]

    result = await get_recent_activity(giveaway_service=mock_giveaway_service, hours=24)

    assert result["success"] is True
    assert result["data"]["period_hours"] == 24
    assert result["data"]["entries"]["total"] == 2
    assert result["data"]["entries"]["successful"] == 1
    assert result["data"]["entries"]["failed"] == 1
    assert result["data"]["entries"]["points_spent"] == 50


@pytest.mark.asyncio
async def test_get_dashboard_data():
    """Test GET /analytics/dashboard endpoint."""
    mock_giveaway_service = AsyncMock()
    mock_scheduler_service = AsyncMock()
    mock_settings_service = AsyncMock()

    mock_giveaway_service.get_giveaway_stats.return_value = {
        "total": 100,
        "active": 75,
        "entered": 25,
        "hidden": 5,
    }
    mock_giveaway_service.get_entry_stats.return_value = {
        "total": 50,
        "successful": 45,
        "failed": 5,
        "success_rate": 90.0,
        "total_points_spent": 2500,
    }

    mock_giveaway = create_mock_giveaway()
    mock_giveaway_service.get_expiring_soon.return_value = [mock_giveaway]

    mock_entry = create_mock_entry()
    mock_giveaway_service.entry_repo.get_recent.return_value = [mock_entry]
    mock_giveaway_service.entry_repo.get_entries_since.return_value = [mock_entry]

    # Mock win count and 30-day stats
    mock_giveaway_service.get_win_count.return_value = 5
    mock_giveaway_service.giveaway_repo.count_entered_since.return_value = 20
    mock_giveaway_service.giveaway_repo.count_won_since.return_value = 2
    mock_giveaway_service.giveaway_repo.get_safety_stats.return_value = {
        "total": 100,
        "safe": 80,
        "unsafe": 10,
        "unknown": 10,
    }

    # Mock scheduler service
    mock_scheduler_service.get_scheduler_status.return_value = {
        "running": False,
        "paused": False,
        "job_count": 0,
        "jobs": [],
    }
    mock_scheduler_service.get_scheduler_stats.return_value = {
        "total_scans": 10,
        "total_entries": 50,
        "total_errors": 1,
        "last_scan_at": None,
        "next_scan_at": None,
        "has_run": False,
    }

    # Mock settings service
    mock_settings = MagicMock()
    mock_settings.automation_enabled = False
    mock_settings.autojoin_enabled = False
    mock_settings.scan_interval_minutes = 30
    mock_settings.phpsessid = None
    mock_settings_service.get_settings.return_value = mock_settings
    mock_settings_service.test_session.return_value = {
        "valid": False,
        "username": None,
        "error": "No session configured",
        "points": None,
    }

    result = await get_dashboard_data(
        giveaway_service=mock_giveaway_service,
        scheduler_service=mock_scheduler_service,
        settings_service=mock_settings_service,
    )

    assert result["success"] is True
    # Dashboard returns active, entered, wins for giveaways (not total)
    assert result["data"]["giveaways"]["active"] == 75
    assert result["data"]["giveaways"]["entered"] == 25
    assert result["data"]["entries"]["total"] == 50


@pytest.mark.asyncio
async def test_get_recent_activity_empty():
    """Test GET /analytics/recent-activity with no entries."""
    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.entry_repo.get_entries_since.return_value = []

    result = await get_recent_activity(giveaway_service=mock_giveaway_service, hours=24)

    assert result["success"] is True
    assert result["data"]["entries"]["total"] == 0
    assert result["data"]["entries"]["points_spent"] == 0


@pytest.mark.asyncio
async def test_get_entry_summary_no_average():
    """Test GET /analytics/entries/summary when no entries."""
    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.get_entry_stats.return_value = {
        "total": 0,
        "successful": 0,
        "failed": 0,
        "success_rate": 0.0,
        "total_points_spent": 0,
        "by_type": {},
    }
    mock_giveaway_service.entry_repo.get_average_points_per_entry.return_value = None

    result = await get_entry_summary(giveaway_service=mock_giveaway_service)

    assert result["success"] is True
    assert result["data"]["average_points_per_entry"] == 0
