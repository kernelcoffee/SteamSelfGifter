"""Unit tests for giveaways API router."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, UTC
from fastapi import HTTPException

from api.routers.giveaways import (
    list_giveaways,
    get_active_giveaways,
    get_expiring_giveaways,
    get_eligible_giveaways,
    get_giveaway_stats,
    get_giveaway,
    sync_giveaways,
    enter_giveaway,
    hide_giveaway,
    search_giveaways,
)
from api.schemas.giveaway import GiveawayScanRequest, GiveawayEntryRequest


def create_mock_giveaway(
    id=1,
    code="TEST123",
    url="https://www.steamgifts.com/giveaway/TEST123/",
    game_name="Test Game",
    price=50,
    copies=1,
    end_time=None,
    is_hidden=False,
    is_entered=False,
    game_id=None,
    is_safe=None,
    safety_score=None,
    discovered_at=None,
    entered_at=None,
):
    """Create a mock giveaway object."""
    mock = MagicMock()
    mock.id = id
    mock.code = code
    mock.url = url
    mock.game_name = game_name
    mock.price = price
    mock.copies = copies
    mock.end_time = end_time or datetime.now(UTC)
    mock.is_hidden = is_hidden
    mock.is_entered = is_entered
    mock.game_id = game_id
    mock.is_safe = is_safe
    mock.safety_score = safety_score
    mock.discovered_at = discovered_at or datetime.now(UTC)
    mock.entered_at = entered_at
    # Additional fields required by GiveawayResponse - explicitly set to None
    mock.is_wishlist = False
    mock.is_won = False
    mock.won_at = None
    mock.game_thumbnail = None
    mock.game_review_score = None
    mock.game_total_reviews = None
    mock.game_review_summary = None
    return mock


@pytest.mark.asyncio
async def test_list_giveaways_active():
    """Test listing giveaways without filters (gets all giveaways)."""
    mock_service = AsyncMock()
    mock_giveaway = create_mock_giveaway()
    mock_service.get_all_giveaways.return_value = [mock_giveaway]
    mock_service.enrich_giveaways_with_game_data.return_value = [mock_giveaway]

    result = await list_giveaways(
        giveaway_service=mock_service,
        min_price=None,
        max_price=None,
        min_score=None,
        min_reviews=None,
        search=None,
        is_entered=None,
        active_only=False,
        limit=50,
        offset=0,
    )

    assert result["success"] is True
    assert result["data"]["count"] == 1
    mock_service.get_all_giveaways.assert_called_once_with(limit=50, offset=0)


@pytest.mark.asyncio
async def test_list_giveaways_search():
    """Test searching giveaways."""
    mock_service = AsyncMock()
    mock_giveaway = create_mock_giveaway(game_name="Portal 2")
    mock_service.search_giveaways.return_value = [mock_giveaway]

    result = await list_giveaways(
        giveaway_service=mock_service,
        min_price=None,
        max_price=None,
        min_score=None,
        min_reviews=None,
        search="Portal",
        is_entered=None,
        limit=50,
    )

    assert result["success"] is True
    mock_service.search_giveaways.assert_called_once_with("Portal", limit=50)


@pytest.mark.asyncio
async def test_list_giveaways_eligible():
    """Test listing eligible (not entered) giveaways."""
    mock_service = AsyncMock()
    mock_giveaway = create_mock_giveaway()
    mock_service.get_eligible_giveaways.return_value = [mock_giveaway]

    result = await list_giveaways(
        giveaway_service=mock_service,
        min_price=50,
        max_price=100,
        min_score=7,
        min_reviews=1000,
        search=None,
        is_entered=False,
        limit=50,
    )

    assert result["success"] is True
    mock_service.get_eligible_giveaways.assert_called_once_with(
        min_price=50,
        max_price=100,
        min_score=7,
        min_reviews=1000,
        limit=50,
    )


@pytest.mark.asyncio
async def test_get_active_giveaways():
    """Test GET /giveaways/active endpoint."""
    mock_service = AsyncMock()
    mock_giveaway = create_mock_giveaway()
    mock_service.get_active_giveaways.return_value = [mock_giveaway]
    mock_service.enrich_giveaways_with_game_data.return_value = [mock_giveaway]

    result = await get_active_giveaways(
        giveaway_service=mock_service,
        limit=50,
        offset=0,
    )

    assert result["success"] is True
    assert result["data"]["count"] == 1


@pytest.mark.asyncio
async def test_get_expiring_giveaways():
    """Test GET /giveaways/expiring endpoint."""
    mock_service = AsyncMock()
    mock_giveaway = create_mock_giveaway()
    mock_service.get_expiring_soon.return_value = [mock_giveaway]

    result = await get_expiring_giveaways(
        giveaway_service=mock_service,
        hours=24,
        limit=20,
    )

    assert result["success"] is True
    assert result["data"]["hours"] == 24
    mock_service.get_expiring_soon.assert_called_once_with(hours=24, limit=20)


@pytest.mark.asyncio
async def test_get_eligible_giveaways():
    """Test GET /giveaways/eligible endpoint."""
    mock_service = AsyncMock()
    mock_giveaway = create_mock_giveaway()
    mock_service.get_eligible_giveaways.return_value = [mock_giveaway]

    result = await get_eligible_giveaways(
        giveaway_service=mock_service,
        min_price=0,
        max_price=None,
        min_score=None,
        min_reviews=None,
        limit=20,
    )

    assert result["success"] is True
    mock_service.get_eligible_giveaways.assert_called_once()


@pytest.mark.asyncio
async def test_get_giveaway_stats():
    """Test GET /giveaways/stats endpoint."""
    mock_service = AsyncMock()
    mock_service.get_giveaway_stats.return_value = {
        "total": 100,
        "active": 75,
        "entered": 25,
        "hidden": 5,
    }

    result = await get_giveaway_stats(giveaway_service=mock_service)

    assert result["success"] is True
    assert result["data"]["total"] == 100
    assert result["data"]["active"] == 75


@pytest.mark.asyncio
async def test_get_giveaway_found():
    """Test GET /giveaways/{code} endpoint when found."""
    mock_service = AsyncMock()
    mock_giveaway = create_mock_giveaway(code="ABC123")
    mock_service.giveaway_repo.get_by_code.return_value = mock_giveaway

    result = await get_giveaway(code="ABC123", giveaway_service=mock_service)

    assert result["success"] is True
    assert result["data"]["code"] == "ABC123"


@pytest.mark.asyncio
async def test_get_giveaway_not_found():
    """Test GET /giveaways/{code} endpoint when not found."""
    mock_service = AsyncMock()
    mock_service.giveaway_repo.get_by_code.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await get_giveaway(code="NOTFOUND", giveaway_service=mock_service)

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_sync_giveaways_success():
    """Test POST /giveaways/sync endpoint."""
    mock_service = AsyncMock()
    mock_service.sync_giveaways.return_value = (5, 3)

    request = GiveawayScanRequest(pages=3)
    result = await sync_giveaways(
        giveaway_service=mock_service,
        request=request,
    )

    assert result["success"] is True
    assert result["data"]["new_count"] == 5
    assert result["data"]["updated_count"] == 3
    assert result["data"]["total_scanned"] == 8
    mock_service.sync_giveaways.assert_called_once_with(pages=3)


@pytest.mark.asyncio
async def test_sync_giveaways_error():
    """Test POST /giveaways/sync endpoint with error."""
    mock_service = AsyncMock()
    mock_service.sync_giveaways.side_effect = Exception("Sync error")

    request = GiveawayScanRequest(pages=3)
    with pytest.raises(HTTPException) as exc_info:
        await sync_giveaways(giveaway_service=mock_service, request=request)

    assert exc_info.value.status_code == 500
    assert "Sync failed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_enter_giveaway_success():
    """Test POST /giveaways/{code}/enter endpoint success."""
    mock_service = AsyncMock()
    mock_scheduler_service = AsyncMock()
    mock_giveaway = create_mock_giveaway(code="TEST123")
    mock_service.giveaway_repo.get_by_code.return_value = mock_giveaway

    mock_entry = MagicMock()
    mock_entry.id = 1
    mock_entry.points_spent = 50
    mock_entry.status = "success"
    mock_entry.error_message = None
    mock_service.enter_giveaway.return_value = mock_entry

    request = GiveawayEntryRequest(entry_type="manual")
    result = await enter_giveaway(
        code="TEST123",
        giveaway_service=mock_service,
        scheduler_service=mock_scheduler_service,
        request=request,
    )

    assert result["success"] is True
    assert result["data"]["success"] is True
    assert result["data"]["points_spent"] == 50
    mock_service.enter_giveaway.assert_called_once_with(
        giveaway_code="TEST123",
        entry_type="manual",
    )
    # Verify win check was scheduled
    mock_scheduler_service.update_win_check_for_new_entry.assert_called_once_with(mock_giveaway.end_time)


@pytest.mark.asyncio
async def test_enter_giveaway_not_found():
    """Test POST /giveaways/{code}/enter endpoint when giveaway not found."""
    mock_service = AsyncMock()
    mock_scheduler_service = AsyncMock()
    mock_service.giveaway_repo.get_by_code.return_value = None

    request = GiveawayEntryRequest(entry_type="manual")
    with pytest.raises(HTTPException) as exc_info:
        await enter_giveaway(
            code="NOTFOUND",
            giveaway_service=mock_service,
            scheduler_service=mock_scheduler_service,
            request=request,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_enter_giveaway_failure():
    """Test POST /giveaways/{code}/enter endpoint when entry fails."""
    mock_service = AsyncMock()
    mock_scheduler_service = AsyncMock()
    mock_giveaway = create_mock_giveaway(code="TEST123")
    mock_service.giveaway_repo.get_by_code.return_value = mock_giveaway

    mock_entry = MagicMock()
    mock_entry.status = "failed"
    mock_entry.error_message = "Not enough points"
    mock_service.enter_giveaway.return_value = mock_entry

    request = GiveawayEntryRequest(entry_type="manual")
    with pytest.raises(HTTPException) as exc_info:
        await enter_giveaway(
            code="TEST123",
            giveaway_service=mock_service,
            scheduler_service=mock_scheduler_service,
            request=request,
        )

    assert exc_info.value.status_code == 400
    assert "Not enough points" in exc_info.value.detail


@pytest.mark.asyncio
async def test_enter_giveaway_no_entry():
    """Test POST /giveaways/{code}/enter endpoint when no entry returned."""
    mock_service = AsyncMock()
    mock_scheduler_service = AsyncMock()
    mock_giveaway = create_mock_giveaway(code="TEST123")
    mock_service.giveaway_repo.get_by_code.return_value = mock_giveaway
    mock_service.enter_giveaway.return_value = None

    request = GiveawayEntryRequest(entry_type="manual")
    with pytest.raises(HTTPException) as exc_info:
        await enter_giveaway(
            code="TEST123",
            giveaway_service=mock_service,
            scheduler_service=mock_scheduler_service,
            request=request,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_hide_giveaway_success():
    """Test POST /giveaways/{code}/hide endpoint success."""
    mock_service = AsyncMock()
    mock_service.hide_giveaway.return_value = True

    result = await hide_giveaway(code="TEST123", giveaway_service=mock_service)

    assert result["success"] is True
    assert result["data"]["code"] == "TEST123"
    mock_service.hide_giveaway.assert_called_once_with("TEST123")


@pytest.mark.asyncio
async def test_hide_giveaway_not_found():
    """Test POST /giveaways/{code}/hide endpoint when not found."""
    mock_service = AsyncMock()
    mock_service.hide_giveaway.return_value = False

    with pytest.raises(HTTPException) as exc_info:
        await hide_giveaway(code="NOTFOUND", giveaway_service=mock_service)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_search_giveaways():
    """Test GET /giveaways/search/{query} endpoint."""
    mock_service = AsyncMock()
    mock_giveaway = create_mock_giveaway(game_name="Portal 2")
    mock_service.search_giveaways.return_value = [mock_giveaway]

    result = await search_giveaways(
        query="Portal",
        giveaway_service=mock_service,
        limit=20,
    )

    assert result["success"] is True
    assert result["data"]["query"] == "Portal"
    assert result["data"]["count"] == 1
    mock_service.search_giveaways.assert_called_once_with("Portal", limit=20)
