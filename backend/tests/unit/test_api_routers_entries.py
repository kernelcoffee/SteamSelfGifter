"""Unit tests for entries API router."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, UTC
from fastapi import HTTPException

from api.routers.entries import (
    list_entries,
    get_entry_stats,
    get_recent_entries,
    get_successful_entries,
    get_failed_entries,
    get_entry_history,
    get_entry,
    get_entries_for_giveaway,
    get_total_points_spent,
)


def create_mock_entry(
    id=1,
    giveaway_id=123,
    points_spent=50,
    entry_type="manual",
    status="success",
    error_message=None,
    entered_at=None,
):
    """Create a mock entry object."""
    mock = MagicMock()
    mock.id = id
    mock.giveaway_id = giveaway_id
    mock.points_spent = points_spent
    mock.entry_type = entry_type
    mock.status = status
    mock.error_message = error_message
    mock.entered_at = entered_at or datetime.now(UTC)
    return mock


def create_mock_giveaway(
    id=123,
    code="TEST123",
    game_name="Test Game",
    game_id=620,
    url="https://www.steamgifts.com/giveaway/TEST123/",
    price=50,
    copies=1,
    end_time=None,
):
    """Create a mock giveaway object."""
    mock = MagicMock()
    mock.id = id
    mock.code = code
    mock.game_name = game_name
    mock.game_id = game_id
    mock.url = url
    mock.price = price
    mock.copies = copies
    mock.end_time = end_time or datetime.now(UTC)
    return mock


@pytest.mark.asyncio
async def test_list_entries_all():
    """Test listing all entries."""
    mock_service = AsyncMock()
    mock_entry = create_mock_entry()
    mock_giveaway = create_mock_giveaway()
    mock_service.get_entry_history.return_value = [mock_entry]
    mock_service.giveaway_repo.get_by_id.return_value = mock_giveaway

    result = await list_entries(
        giveaway_service=mock_service,
        status_filter=None,
        entry_type=None,
        limit=50,
        offset=0,
    )

    assert result["success"] is True
    assert result["data"]["count"] == 1
    mock_service.get_entry_history.assert_called_once_with(limit=50)


@pytest.mark.asyncio
async def test_list_entries_by_status():
    """Test filtering entries by status."""
    mock_service = AsyncMock()
    mock_entry = create_mock_entry(status="success")
    mock_giveaway = create_mock_giveaway()
    mock_service.get_entry_history.return_value = [mock_entry]
    mock_service.giveaway_repo.get_by_id.return_value = mock_giveaway

    result = await list_entries(
        giveaway_service=mock_service,
        status_filter="success",
        entry_type=None,
        limit=50,
        offset=0,
    )

    assert result["success"] is True
    mock_service.get_entry_history.assert_called_once_with(limit=50, status="success")


@pytest.mark.asyncio
async def test_list_entries_by_type():
    """Test filtering entries by type."""
    mock_service = AsyncMock()
    mock_entry = create_mock_entry(entry_type="auto")
    mock_giveaway = create_mock_giveaway()
    mock_service.entry_repo.get_by_entry_type.return_value = [mock_entry]
    mock_service.giveaway_repo.get_by_id.return_value = mock_giveaway

    result = await list_entries(
        giveaway_service=mock_service,
        status_filter=None,
        entry_type="auto",
        limit=50,
        offset=0,
    )

    assert result["success"] is True
    mock_service.entry_repo.get_by_entry_type.assert_called_once_with("auto", limit=50)


@pytest.mark.asyncio
async def test_get_entry_stats():
    """Test GET /entries/stats endpoint."""
    mock_service = AsyncMock()
    mock_service.get_entry_stats.return_value = {
        "total": 100,
        "successful": 85,
        "failed": 15,
        "total_points_spent": 4250,
        "by_type": {"manual": 25, "auto": 60, "wishlist": 15},
        "success_rate": 85.0,
    }

    result = await get_entry_stats(giveaway_service=mock_service)

    assert result["success"] is True
    assert result["data"]["total"] == 100
    assert result["data"]["successful"] == 85
    assert result["data"]["success_rate"] == 85.0


@pytest.mark.asyncio
async def test_get_recent_entries():
    """Test GET /entries/recent endpoint."""
    mock_service = AsyncMock()
    mock_entry = create_mock_entry()
    mock_service.entry_repo.get_recent.return_value = [mock_entry]

    result = await get_recent_entries(giveaway_service=mock_service, limit=10)

    assert result["success"] is True
    mock_service.entry_repo.get_recent.assert_called_once_with(limit=10)


@pytest.mark.asyncio
async def test_get_successful_entries():
    """Test GET /entries/successful endpoint."""
    mock_service = AsyncMock()
    mock_entry = create_mock_entry(status="success")
    mock_service.entry_repo.get_successful.return_value = [mock_entry]

    result = await get_successful_entries(giveaway_service=mock_service, limit=50)

    assert result["success"] is True
    mock_service.entry_repo.get_successful.assert_called_once()


@pytest.mark.asyncio
async def test_get_failed_entries():
    """Test GET /entries/failed endpoint."""
    mock_service = AsyncMock()
    mock_entry = create_mock_entry(status="failed", error_message="Not enough points")
    mock_service.entry_repo.get_recent_failures.return_value = [mock_entry]

    result = await get_failed_entries(giveaway_service=mock_service, limit=50)

    assert result["success"] is True
    mock_service.entry_repo.get_recent_failures.assert_called_once_with(limit=50)


@pytest.mark.asyncio
async def test_get_entry_history():
    """Test GET /entries/history endpoint."""
    mock_service = AsyncMock()
    mock_entry = create_mock_entry()
    mock_giveaway = create_mock_giveaway()

    mock_service.entry_repo.get_recent.return_value = [mock_entry]
    mock_service.giveaway_repo.get_by_id.return_value = mock_giveaway

    result = await get_entry_history(giveaway_service=mock_service, limit=20)

    assert result["success"] is True
    assert result["data"]["count"] == 1
    assert result["data"]["entries"][0]["game_name"] == "Test Game"


@pytest.mark.asyncio
async def test_get_entry_history_no_giveaway():
    """Test GET /entries/history when giveaway not found."""
    mock_service = AsyncMock()
    mock_entry = create_mock_entry()

    mock_service.entry_repo.get_recent.return_value = [mock_entry]
    mock_service.giveaway_repo.get_by_id.return_value = None

    result = await get_entry_history(giveaway_service=mock_service, limit=20)

    assert result["success"] is True
    assert result["data"]["count"] == 0  # Entry without giveaway is skipped


@pytest.mark.asyncio
async def test_get_entry_found():
    """Test GET /entries/{entry_id} endpoint when found."""
    mock_service = AsyncMock()
    mock_entry = create_mock_entry(id=123)
    mock_service.entry_repo.get_by_id.return_value = mock_entry

    result = await get_entry(entry_id=123, giveaway_service=mock_service)

    assert result["success"] is True
    assert result["data"]["id"] == 123


@pytest.mark.asyncio
async def test_get_entry_not_found():
    """Test GET /entries/{entry_id} endpoint when not found."""
    mock_service = AsyncMock()
    mock_service.entry_repo.get_by_id.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await get_entry(entry_id=999, giveaway_service=mock_service)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_entries_for_giveaway_found():
    """Test GET /entries/giveaway/{giveaway_id} endpoint when found."""
    mock_service = AsyncMock()
    mock_entry = create_mock_entry(giveaway_id=123)
    mock_service.entry_repo.get_by_giveaway.return_value = mock_entry

    result = await get_entries_for_giveaway(giveaway_id=123, giveaway_service=mock_service)

    assert result["success"] is True
    assert result["data"]["count"] == 1
    assert result["data"]["giveaway_id"] == 123


@pytest.mark.asyncio
async def test_get_entries_for_giveaway_not_found():
    """Test GET /entries/giveaway/{giveaway_id} endpoint when not found."""
    mock_service = AsyncMock()
    mock_service.entry_repo.get_by_giveaway.return_value = None

    result = await get_entries_for_giveaway(giveaway_id=999, giveaway_service=mock_service)

    assert result["success"] is True
    assert result["data"]["count"] == 0


@pytest.mark.asyncio
async def test_get_total_points_spent():
    """Test GET /entries/points/total endpoint."""
    mock_service = AsyncMock()
    mock_service.entry_repo.get_total_points_spent.return_value = 5000
    mock_service.entry_repo.get_total_points_by_status.return_value = 4500

    result = await get_total_points_spent(giveaway_service=mock_service)

    assert result["success"] is True
    assert result["data"]["total_points_spent"] == 5000
    assert result["data"]["successful_points_spent"] == 4500
