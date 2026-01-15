"""Games API router for game data management.

This module provides REST API endpoints for game operations,
including fetching, searching, refreshing, and viewing statistics.
"""

from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Query, status

from api.schemas.common import create_success_response
from api.schemas.game import (
    GameResponse,
    GameRefreshResponse,
    GameStats,
)
from api.dependencies import GameServiceDep

router = APIRouter()


@router.get(
    "/",
    response_model=Dict[str, Any],
    summary="List games",
    description="Get a list of cached games with optional filtering.",
)
async def list_games(
    game_service: GameServiceDep,
    type: Optional[str] = Query(default=None, description="Filter by type (game, dlc, bundle)"),
    min_score: Optional[int] = Query(default=None, ge=0, le=10, description="Minimum review score"),
    min_reviews: Optional[int] = Query(default=None, ge=0, description="Minimum reviews"),
    search: Optional[str] = Query(default=None, description="Search by game name"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum results"),
) -> Dict[str, Any]:
    """
    List cached games with filtering options.

    Returns:
        Success response with list of games

    Example response:
        {
            "success": true,
            "data": {
                "games": [...],
                "count": 50
            }
        }
    """
    if search:
        # Search takes precedence
        games = await game_service.search_games(search, limit=limit)
    elif min_score is not None or min_reviews is not None:
        # Filter by rating
        games = await game_service.get_highly_rated_games(
            min_score=min_score or 0,
            min_reviews=min_reviews or 0,
            limit=limit,
        )
    elif type:
        # Filter by type
        games = await game_service.get_games_by_type(type, limit=limit)
    else:
        # Get all games (via repo directly since service doesn't have get_all)
        games = await game_service.repo.get_all(limit=limit)

    # Convert to response format
    game_list = [
        GameResponse.model_validate(g).model_dump()
        for g in games
    ]

    return create_success_response(
        data={
            "games": game_list,
            "count": len(game_list),
        }
    )


@router.get(
    "/stats",
    response_model=Dict[str, Any],
    summary="Get game statistics",
    description="Get statistics about games in the cache.",
)
async def get_game_stats(
    game_service: GameServiceDep,
) -> Dict[str, Any]:
    """
    Get game cache statistics.

    Returns:
        Success response with game statistics
    """
    stats = await game_service.get_game_cache_stats()

    # Format for response
    by_type = stats.get("by_type", {})
    response = GameStats(
        total=stats.get("total", 0),
        games=by_type.get("game", 0),
        dlc=by_type.get("dlc", 0),
        bundles=by_type.get("bundle", 0),
    )

    return create_success_response(data=response.model_dump())


@router.get(
    "/search/{query}",
    response_model=Dict[str, Any],
    summary="Search games",
    description="Search cached games by name.",
)
async def search_games(
    query: str,
    game_service: GameServiceDep,
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results"),
) -> Dict[str, Any]:
    """
    Search games by name.

    Args:
        query: Search query
        limit: Maximum results

    Returns:
        Success response with matching games
    """
    games = await game_service.search_games(query, limit=limit)
    game_list = [
        GameResponse.model_validate(g).model_dump()
        for g in games
    ]

    return create_success_response(
        data={
            "games": game_list,
            "count": len(game_list),
            "query": query,
        }
    )


@router.get(
    "/highly-rated",
    response_model=Dict[str, Any],
    summary="Get highly rated games",
    description="Get games with high review scores.",
)
async def get_highly_rated_games(
    game_service: GameServiceDep,
    min_score: int = Query(default=8, ge=0, le=10, description="Minimum review score"),
    min_reviews: int = Query(default=1000, ge=0, description="Minimum reviews"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum results"),
) -> Dict[str, Any]:
    """
    Get highly rated games.

    Returns:
        Success response with highly rated games
    """
    games = await game_service.get_highly_rated_games(
        min_score=min_score,
        min_reviews=min_reviews,
        limit=limit,
    )
    game_list = [
        GameResponse.model_validate(g).model_dump()
        for g in games
    ]

    return create_success_response(
        data={
            "games": game_list,
            "count": len(game_list),
            "min_score": min_score,
            "min_reviews": min_reviews,
        }
    )


@router.get(
    "/{app_id}",
    response_model=Dict[str, Any],
    summary="Get game by App ID",
    description="Get a specific game by Steam App ID. Fetches from Steam if not cached.",
)
async def get_game(
    app_id: int,
    game_service: GameServiceDep,
    force_refresh: bool = Query(default=False, description="Force refresh from Steam API"),
) -> Dict[str, Any]:
    """
    Get a specific game by App ID.

    Args:
        app_id: Steam App ID
        force_refresh: Force refresh from Steam API

    Returns:
        Success response with game details

    Raises:
        HTTPException: 404 if game not found
    """
    game = await game_service.get_or_fetch_game(app_id, force_refresh=force_refresh)
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game with App ID {app_id} not found"
        )

    return create_success_response(
        data=GameResponse.model_validate(game).model_dump()
    )


@router.post(
    "/{app_id}/refresh",
    response_model=Dict[str, Any],
    summary="Refresh game data",
    description="Force refresh game data from Steam API.",
)
async def refresh_game(
    app_id: int,
    game_service: GameServiceDep,
) -> Dict[str, Any]:
    """
    Refresh game data from Steam API.

    Args:
        app_id: Steam App ID

    Returns:
        Success response with refresh result
    """
    try:
        game = await game_service.get_or_fetch_game(app_id, force_refresh=True)

        if game:
            response = GameRefreshResponse(
                refreshed=True,
                message="Game data refreshed successfully",
                last_refreshed_at=game.last_refreshed_at,
            )
        else:
            response = GameRefreshResponse(
                refreshed=False,
                message=f"Game with App ID {app_id} not found on Steam",
                last_refreshed_at=None,
            )

        return create_success_response(data=response.model_dump())

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Refresh failed: {str(e)}"
        )


@router.post(
    "/refresh-stale",
    response_model=Dict[str, Any],
    summary="Refresh stale games",
    description="Refresh games with stale cached data.",
)
async def refresh_stale_games(
    game_service: GameServiceDep,
    limit: int = Query(default=10, ge=1, le=50, description="Maximum games to refresh"),
) -> Dict[str, Any]:
    """
    Refresh stale cached games.

    Args:
        limit: Maximum number of games to refresh

    Returns:
        Success response with refresh count
    """
    try:
        count = await game_service.refresh_stale_games(limit=limit)

        return create_success_response(
            data={
                "refreshed": count,
                "message": f"Refreshed {count} stale games",
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Refresh failed: {str(e)}"
        )


@router.post(
    "/bulk-cache",
    response_model=Dict[str, Any],
    summary="Bulk cache games",
    description="Cache multiple games by their Steam App IDs.",
)
async def bulk_cache_games(
    app_ids: List[int],
    game_service: GameServiceDep,
) -> Dict[str, Any]:
    """
    Cache multiple games from Steam API.

    Args:
        app_ids: List of Steam App IDs to cache

    Returns:
        Success response with cache count
    """
    if not app_ids:
        return create_success_response(
            data={
                "cached": 0,
                "message": "No app IDs provided",
            }
        )

    if len(app_ids) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 50 app IDs per request"
        )

    try:
        count = await game_service.bulk_cache_games(app_ids)

        return create_success_response(
            data={
                "cached": count,
                "total_requested": len(app_ids),
                "message": f"Cached {count} of {len(app_ids)} games",
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk cache failed: {str(e)}"
        )
