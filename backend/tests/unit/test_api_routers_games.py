"""Unit tests for games API router."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, UTC
from fastapi import HTTPException

from api.routers.games import (
    list_games,
    get_game_stats,
    search_games,
    get_highly_rated_games,
    get_game,
    refresh_game,
    refresh_stale_games,
    bulk_cache_games,
)


def create_mock_game(
    id=620,
    name="Portal 2",
    type="game",
    release_date=None,
    review_score=9,
    total_positive=150000,
    total_negative=5000,
    total_reviews=155000,
    is_bundle=False,
    bundle_content=None,
    game_id=None,
    description=None,
    price=None,
    last_refreshed_at=None,
):
    """Create a mock game object."""
    mock = MagicMock()
    mock.id = id
    mock.name = name
    mock.type = type
    mock.release_date = release_date
    mock.review_score = review_score
    mock.total_positive = total_positive
    mock.total_negative = total_negative
    mock.total_reviews = total_reviews
    mock.is_bundle = is_bundle
    mock.bundle_content = bundle_content
    mock.game_id = game_id
    mock.description = description
    mock.price = price
    mock.last_refreshed_at = last_refreshed_at or datetime.now(UTC)
    return mock


@pytest.mark.asyncio
async def test_list_games_all():
    """Test listing all games."""
    mock_service = AsyncMock()
    mock_game = create_mock_game()
    mock_service.repo.get_all.return_value = [mock_game]

    result = await list_games(
        game_service=mock_service,
        type=None,
        min_score=None,
        min_reviews=None,
        search=None,
        limit=50,
    )

    assert result["success"] is True
    assert result["data"]["count"] == 1
    mock_service.repo.get_all.assert_called_once_with(limit=50)


@pytest.mark.asyncio
async def test_list_games_search():
    """Test searching games."""
    mock_service = AsyncMock()
    mock_game = create_mock_game()
    mock_service.search_games.return_value = [mock_game]

    result = await list_games(
        game_service=mock_service,
        type=None,
        min_score=None,
        min_reviews=None,
        search="Portal",
        limit=50,
    )

    assert result["success"] is True
    mock_service.search_games.assert_called_once_with("Portal", limit=50)


@pytest.mark.asyncio
async def test_list_games_by_type():
    """Test filtering games by type."""
    mock_service = AsyncMock()
    mock_game = create_mock_game(type="dlc")
    mock_service.get_games_by_type.return_value = [mock_game]

    result = await list_games(
        game_service=mock_service,
        type="dlc",
        min_score=None,
        min_reviews=None,
        search=None,
        limit=50,
    )

    assert result["success"] is True
    mock_service.get_games_by_type.assert_called_once_with("dlc", limit=50)


@pytest.mark.asyncio
async def test_list_games_by_rating():
    """Test filtering games by rating."""
    mock_service = AsyncMock()
    mock_game = create_mock_game(review_score=9)
    mock_service.get_highly_rated_games.return_value = [mock_game]

    result = await list_games(
        game_service=mock_service,
        type=None,
        min_score=8,
        min_reviews=1000,
        search=None,
        limit=50,
    )

    assert result["success"] is True
    mock_service.get_highly_rated_games.assert_called_once_with(
        min_score=8,
        min_reviews=1000,
        limit=50,
    )


@pytest.mark.asyncio
async def test_get_game_stats():
    """Test GET /games/stats endpoint."""
    mock_service = AsyncMock()
    mock_service.get_game_cache_stats.return_value = {
        "total": 500,
        "by_type": {"game": 450, "dlc": 40, "bundle": 10},
        "stale_count": 20,
    }

    result = await get_game_stats(game_service=mock_service)

    assert result["success"] is True
    assert result["data"]["total"] == 500
    assert result["data"]["games"] == 450
    assert result["data"]["dlc"] == 40


@pytest.mark.asyncio
async def test_search_games():
    """Test GET /games/search/{query} endpoint."""
    mock_service = AsyncMock()
    mock_game = create_mock_game()
    mock_service.search_games.return_value = [mock_game]

    result = await search_games(
        query="Portal",
        game_service=mock_service,
        limit=20,
    )

    assert result["success"] is True
    assert result["data"]["query"] == "Portal"
    mock_service.search_games.assert_called_once_with("Portal", limit=20)


@pytest.mark.asyncio
async def test_get_highly_rated_games():
    """Test GET /games/highly-rated endpoint."""
    mock_service = AsyncMock()
    mock_game = create_mock_game(review_score=9)
    mock_service.get_highly_rated_games.return_value = [mock_game]

    result = await get_highly_rated_games(
        game_service=mock_service,
        min_score=8,
        min_reviews=1000,
        limit=50,
    )

    assert result["success"] is True
    assert result["data"]["min_score"] == 8
    assert result["data"]["min_reviews"] == 1000


@pytest.mark.asyncio
async def test_get_game_found():
    """Test GET /games/{app_id} endpoint when found."""
    mock_service = AsyncMock()
    mock_game = create_mock_game(id=620, name="Portal 2")
    mock_service.get_or_fetch_game.return_value = mock_game

    result = await get_game(
        app_id=620,
        game_service=mock_service,
        force_refresh=False,
    )

    assert result["success"] is True
    assert result["data"]["id"] == 620
    mock_service.get_or_fetch_game.assert_called_once_with(620, force_refresh=False)


@pytest.mark.asyncio
async def test_get_game_not_found():
    """Test GET /games/{app_id} endpoint when not found."""
    mock_service = AsyncMock()
    mock_service.get_or_fetch_game.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await get_game(
            app_id=999999,
            game_service=mock_service,
            force_refresh=False,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_game_force_refresh():
    """Test GET /games/{app_id} with force refresh."""
    mock_service = AsyncMock()
    mock_game = create_mock_game()
    mock_service.get_or_fetch_game.return_value = mock_game

    result = await get_game(
        app_id=620,
        game_service=mock_service,
        force_refresh=True,
    )

    assert result["success"] is True
    mock_service.get_or_fetch_game.assert_called_once_with(620, force_refresh=True)


@pytest.mark.asyncio
async def test_refresh_game_success():
    """Test POST /games/{app_id}/refresh endpoint success."""
    mock_service = AsyncMock()
    mock_game = create_mock_game()
    mock_service.get_or_fetch_game.return_value = mock_game

    result = await refresh_game(app_id=620, game_service=mock_service)

    assert result["success"] is True
    assert result["data"]["refreshed"] is True
    mock_service.get_or_fetch_game.assert_called_once_with(620, force_refresh=True)


@pytest.mark.asyncio
async def test_refresh_game_not_found():
    """Test POST /games/{app_id}/refresh endpoint when not found."""
    mock_service = AsyncMock()
    mock_service.get_or_fetch_game.return_value = None

    result = await refresh_game(app_id=999999, game_service=mock_service)

    assert result["success"] is True
    assert result["data"]["refreshed"] is False


@pytest.mark.asyncio
async def test_refresh_game_error():
    """Test POST /games/{app_id}/refresh endpoint with error."""
    mock_service = AsyncMock()
    mock_service.get_or_fetch_game.side_effect = Exception("API error")

    with pytest.raises(HTTPException) as exc_info:
        await refresh_game(app_id=620, game_service=mock_service)

    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_refresh_stale_games():
    """Test POST /games/refresh-stale endpoint."""
    mock_service = AsyncMock()
    mock_service.refresh_stale_games.return_value = 5

    result = await refresh_stale_games(game_service=mock_service, limit=10)

    assert result["success"] is True
    assert result["data"]["refreshed"] == 5
    mock_service.refresh_stale_games.assert_called_once_with(limit=10)


@pytest.mark.asyncio
async def test_refresh_stale_games_error():
    """Test POST /games/refresh-stale endpoint with error."""
    mock_service = AsyncMock()
    mock_service.refresh_stale_games.side_effect = Exception("Refresh error")

    with pytest.raises(HTTPException) as exc_info:
        await refresh_stale_games(game_service=mock_service, limit=10)

    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_bulk_cache_games():
    """Test POST /games/bulk-cache endpoint."""
    mock_service = AsyncMock()
    mock_service.bulk_cache_games.return_value = 3

    result = await bulk_cache_games(
        app_ids=[620, 730, 440],
        game_service=mock_service,
    )

    assert result["success"] is True
    assert result["data"]["cached"] == 3
    assert result["data"]["total_requested"] == 3
    mock_service.bulk_cache_games.assert_called_once_with([620, 730, 440])


@pytest.mark.asyncio
async def test_bulk_cache_games_empty():
    """Test POST /games/bulk-cache endpoint with empty list."""
    mock_service = AsyncMock()

    result = await bulk_cache_games(app_ids=[], game_service=mock_service)

    assert result["success"] is True
    assert result["data"]["cached"] == 0


@pytest.mark.asyncio
async def test_bulk_cache_games_too_many():
    """Test POST /games/bulk-cache endpoint with too many IDs."""
    mock_service = AsyncMock()
    app_ids = list(range(100))  # 100 IDs, exceeds limit of 50

    with pytest.raises(HTTPException) as exc_info:
        await bulk_cache_games(app_ids=app_ids, game_service=mock_service)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_bulk_cache_games_error():
    """Test POST /games/bulk-cache endpoint with error."""
    mock_service = AsyncMock()
    mock_service.bulk_cache_games.side_effect = Exception("Cache error")

    with pytest.raises(HTTPException) as exc_info:
        await bulk_cache_games(app_ids=[620], game_service=mock_service)

    assert exc_info.value.status_code == 500
