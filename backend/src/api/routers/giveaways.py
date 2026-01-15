"""Giveaways API router for giveaway management.

This module provides REST API endpoints for giveaway operations,
including listing, filtering, syncing, entering, and hiding giveaways.
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, status

from api.schemas.common import create_success_response
from api.schemas.giveaway import (
    GiveawayResponse,
    GiveawayFilter,
    GiveawayScanRequest,
    GiveawayScanResponse,
    GiveawayEntryRequest,
    GiveawayEntryResponse,
    GiveawayStats,
)
from api.dependencies import GiveawayServiceDep, SchedulerServiceDep

router = APIRouter()


@router.get(
    "",
    response_model=Dict[str, Any],
    summary="List giveaways",
    description="Get a list of giveaways with optional filtering.",
)
async def list_giveaways(
    giveaway_service: GiveawayServiceDep,
    min_price: Optional[int] = Query(default=None, ge=0, description="Minimum price"),
    max_price: Optional[int] = Query(default=None, ge=0, description="Maximum price"),
    min_score: Optional[int] = Query(default=None, ge=0, le=10, description="Minimum review score"),
    min_reviews: Optional[int] = Query(default=None, ge=0, description="Minimum reviews"),
    search: Optional[str] = Query(default=None, description="Search by game name"),
    is_entered: Optional[bool] = Query(default=None, description="Filter by entry status"),
    active_only: bool = Query(default=False, description="Only show non-expired giveaways"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
) -> Dict[str, Any]:
    """
    List giveaways with filtering options.

    Returns:
        Success response with list of giveaways

    Example response:
        {
            "success": true,
            "data": {
                "giveaways": [...],
                "count": 50
            }
        }
    """
    if search:
        # Search takes precedence
        giveaways = await giveaway_service.search_giveaways(search, limit=limit)
    elif is_entered is True:
        # Get entered giveaways
        giveaways = await giveaway_service.get_entered_giveaways(
            limit=limit, active_only=active_only
        )
    elif is_entered is False:
        # Get eligible (not entered) giveaways
        giveaways = await giveaway_service.get_eligible_giveaways(
            min_price=min_price or 0,
            max_price=max_price,
            min_score=min_score,
            min_reviews=min_reviews,
            limit=limit,
        )
    else:
        # Get all giveaways (including expired) when no specific filter
        giveaways = await giveaway_service.get_all_giveaways(limit=limit, offset=offset)

    # Enrich with game data (thumbnails, reviews)
    giveaways = await giveaway_service.enrich_giveaways_with_game_data(giveaways)

    # Convert to response format
    giveaway_list = [
        GiveawayResponse.model_validate(g).model_dump()
        for g in giveaways
    ]

    return create_success_response(
        data={
            "giveaways": giveaway_list,
            "count": len(giveaway_list),
        }
    )


@router.get(
    "/active",
    response_model=Dict[str, Any],
    summary="Get active giveaways",
    description="Get all active (non-expired) giveaways.",
)
async def get_active_giveaways(
    giveaway_service: GiveawayServiceDep,
    min_score: Optional[int] = Query(default=None, ge=0, le=10, description="Minimum review score (0-10)"),
    is_safe: Optional[bool] = Query(default=None, description="Filter by safety status (true=safe, false=unsafe)"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
) -> Dict[str, Any]:
    """
    Get active giveaways.

    Returns:
        Success response with list of active giveaways
    """
    giveaways = await giveaway_service.get_active_giveaways(
        limit=limit, offset=offset, min_score=min_score, is_safe=is_safe
    )

    # Enrich with game data (thumbnails, reviews)
    giveaways = await giveaway_service.enrich_giveaways_with_game_data(giveaways)

    giveaway_list = [
        GiveawayResponse.model_validate(g).model_dump()
        for g in giveaways
    ]

    return create_success_response(
        data={
            "giveaways": giveaway_list,
            "count": len(giveaway_list),
        }
    )


@router.get(
    "/wishlist",
    response_model=Dict[str, Any],
    summary="Get wishlist giveaways",
    description="Get active giveaways for games on user's Steam wishlist.",
)
async def get_wishlist_giveaways(
    giveaway_service: GiveawayServiceDep,
    limit: int = Query(default=50, ge=1, le=200, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
) -> Dict[str, Any]:
    """
    Get wishlist giveaways.

    Returns:
        Success response with list of wishlist giveaways
    """
    giveaways = await giveaway_service.giveaway_repo.get_wishlist(limit=limit, offset=offset)

    # Enrich with game data (thumbnails, reviews)
    giveaways = await giveaway_service.enrich_giveaways_with_game_data(giveaways)

    giveaway_list = [
        GiveawayResponse.model_validate(g).model_dump()
        for g in giveaways
    ]

    return create_success_response(
        data={
            "giveaways": giveaway_list,
            "count": len(giveaway_list),
        }
    )


@router.get(
    "/won",
    response_model=Dict[str, Any],
    summary="Get won giveaways",
    description="Get giveaways that the user has won.",
)
async def get_won_giveaways(
    giveaway_service: GiveawayServiceDep,
    limit: int = Query(default=50, ge=1, le=200, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
) -> Dict[str, Any]:
    """
    Get won giveaways.

    Returns:
        Success response with list of won giveaways
    """
    giveaways = await giveaway_service.get_won_giveaways(limit=limit, offset=offset)

    # Enrich with game data (thumbnails, reviews)
    giveaways = await giveaway_service.enrich_giveaways_with_game_data(giveaways)

    # Get total count
    total_wins = await giveaway_service.get_win_count()

    giveaway_list = [
        GiveawayResponse.model_validate(g).model_dump()
        for g in giveaways
    ]

    return create_success_response(
        data={
            "giveaways": giveaway_list,
            "count": len(giveaway_list),
            "total_wins": total_wins,
        }
    )


@router.get(
    "/expiring",
    response_model=Dict[str, Any],
    summary="Get expiring giveaways",
    description="Get giveaways expiring within specified hours.",
)
async def get_expiring_giveaways(
    giveaway_service: GiveawayServiceDep,
    hours: int = Query(default=24, ge=1, le=168, description="Hours until expiration"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results"),
) -> Dict[str, Any]:
    """
    Get giveaways expiring soon.

    Returns:
        Success response with list of expiring giveaways
    """
    giveaways = await giveaway_service.get_expiring_soon(hours=hours, limit=limit)
    giveaway_list = [
        GiveawayResponse.model_validate(g).model_dump()
        for g in giveaways
    ]

    return create_success_response(
        data={
            "giveaways": giveaway_list,
            "count": len(giveaway_list),
            "hours": hours,
        }
    )


@router.get(
    "/eligible",
    response_model=Dict[str, Any],
    summary="Get eligible giveaways",
    description="Get giveaways that match auto-join criteria.",
)
async def get_eligible_giveaways(
    giveaway_service: GiveawayServiceDep,
    min_price: int = Query(default=0, ge=0, description="Minimum price"),
    max_price: Optional[int] = Query(default=None, ge=0, description="Maximum price"),
    min_score: Optional[int] = Query(default=None, ge=0, le=10, description="Minimum review score"),
    min_reviews: Optional[int] = Query(default=None, ge=0, description="Minimum reviews"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results"),
) -> Dict[str, Any]:
    """
    Get eligible giveaways based on criteria.

    Returns:
        Success response with list of eligible giveaways
    """
    giveaways = await giveaway_service.get_eligible_giveaways(
        min_price=min_price,
        max_price=max_price,
        min_score=min_score,
        min_reviews=min_reviews,
        limit=limit,
    )
    giveaway_list = [
        GiveawayResponse.model_validate(g).model_dump()
        for g in giveaways
    ]

    return create_success_response(
        data={
            "giveaways": giveaway_list,
            "count": len(giveaway_list),
        }
    )


@router.get(
    "/stats",
    response_model=Dict[str, Any],
    summary="Get giveaway statistics",
    description="Get statistics about giveaways in the database.",
)
async def get_giveaway_stats(
    giveaway_service: GiveawayServiceDep,
) -> Dict[str, Any]:
    """
    Get giveaway statistics.

    Returns:
        Success response with giveaway statistics
    """
    stats = await giveaway_service.get_giveaway_stats()
    return create_success_response(data=stats)


@router.get(
    "/{code}",
    response_model=Dict[str, Any],
    summary="Get giveaway by code",
    description="Get a specific giveaway by its SteamGifts code.",
)
async def get_giveaway(
    code: str,
    giveaway_service: GiveawayServiceDep,
) -> Dict[str, Any]:
    """
    Get a specific giveaway by code.

    Args:
        code: SteamGifts giveaway code

    Returns:
        Success response with giveaway details

    Raises:
        HTTPException: 404 if giveaway not found
    """
    giveaway = await giveaway_service.giveaway_repo.get_by_code(code)
    if not giveaway:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Giveaway with code '{code}' not found"
        )

    return create_success_response(
        data=GiveawayResponse.model_validate(giveaway).model_dump()
    )


@router.post(
    "/sync",
    response_model=Dict[str, Any],
    summary="Sync giveaways",
    description="Sync giveaways from SteamGifts. Requires authentication.",
)
async def sync_giveaways(
    giveaway_service: GiveawayServiceDep,
    request: GiveawayScanRequest = GiveawayScanRequest(),
) -> Dict[str, Any]:
    """
    Sync giveaways from SteamGifts.

    Args:
        request: Scan request with number of pages

    Returns:
        Success response with sync results
    """
    try:
        new_count, updated_count = await giveaway_service.sync_giveaways(
            pages=request.pages
        )

        response = GiveawayScanResponse(
            new_count=new_count,
            updated_count=updated_count,
            total_scanned=new_count + updated_count,
        )

        return create_success_response(data=response.model_dump())

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}"
        )


@router.post(
    "/{code}/enter",
    response_model=Dict[str, Any],
    summary="Enter a giveaway",
    description="Enter a specific giveaway. Requires authentication.",
)
async def enter_giveaway(
    code: str,
    giveaway_service: GiveawayServiceDep,
    scheduler_service: SchedulerServiceDep,
    request: GiveawayEntryRequest = GiveawayEntryRequest(),
) -> Dict[str, Any]:
    """
    Enter a giveaway.

    Args:
        code: SteamGifts giveaway code
        request: Entry request with entry type

    Returns:
        Success response with entry result

    Raises:
        HTTPException: 400 if entry fails, 404 if giveaway not found
    """
    # Check if giveaway exists
    giveaway = await giveaway_service.giveaway_repo.get_by_code(code)
    if not giveaway:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Giveaway with code '{code}' not found"
        )

    # Try to enter
    entry = await giveaway_service.enter_giveaway(
        giveaway_code=code,
        entry_type=request.entry_type,
    )

    if entry and entry.status == "success":
        # Schedule win check for this giveaway if needed
        await scheduler_service.update_win_check_for_new_entry(giveaway.end_time)

        response = GiveawayEntryResponse(
            success=True,
            points_spent=entry.points_spent,
            message="Successfully entered giveaway",
            entry_id=entry.id,
        )
        return create_success_response(data=response.model_dump())
    else:
        # Get error message from entry if available
        error_msg = "Entry failed"
        if entry and entry.error_message:
            error_msg = entry.error_message

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )


@router.post(
    "/{code}/hide",
    response_model=Dict[str, Any],
    summary="Hide a giveaway",
    description="Hide a giveaway from recommendations.",
)
async def hide_giveaway(
    code: str,
    giveaway_service: GiveawayServiceDep,
) -> Dict[str, Any]:
    """
    Hide a giveaway.

    Args:
        code: SteamGifts giveaway code

    Returns:
        Success response confirming hide

    Raises:
        HTTPException: 404 if giveaway not found
    """
    success = await giveaway_service.hide_giveaway(code)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Giveaway with code '{code}' not found"
        )

    return create_success_response(
        data={
            "message": "Giveaway hidden",
            "code": code,
        }
    )


@router.post(
    "/{code}/unhide",
    response_model=Dict[str, Any],
    summary="Unhide a giveaway",
    description="Unhide a previously hidden giveaway.",
)
async def unhide_giveaway(
    code: str,
    giveaway_service: GiveawayServiceDep,
) -> Dict[str, Any]:
    """
    Unhide a giveaway.

    Args:
        code: SteamGifts giveaway code

    Returns:
        Success response confirming unhide

    Raises:
        HTTPException: 404 if giveaway not found
    """
    success = await giveaway_service.unhide_giveaway(code)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Giveaway with code '{code}' not found"
        )

    return create_success_response(
        data={
            "message": "Giveaway unhidden",
            "code": code,
        }
    )


@router.post(
    "/{code}/remove-entry",
    response_model=Dict[str, Any],
    summary="Remove entry from a giveaway",
    description="Remove an entry from a giveaway you previously entered.",
)
async def remove_giveaway_entry(
    code: str,
    giveaway_service: GiveawayServiceDep,
) -> Dict[str, Any]:
    """
    Remove an entry from a giveaway.

    Args:
        code: SteamGifts giveaway code

    Returns:
        Success response confirming entry removal

    Raises:
        HTTPException: 404 if giveaway not found or not entered
    """
    success = await giveaway_service.remove_entry(code)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Giveaway with code '{code}' not found or not entered"
        )

    return create_success_response(
        data={
            "message": "Entry removed",
            "code": code,
        }
    )


@router.get(
    "/search/{query}",
    response_model=Dict[str, Any],
    summary="Search giveaways",
    description="Search giveaways by game name.",
)
async def search_giveaways(
    query: str,
    giveaway_service: GiveawayServiceDep,
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results"),
) -> Dict[str, Any]:
    """
    Search giveaways by game name.

    Args:
        query: Search query
        limit: Maximum results

    Returns:
        Success response with matching giveaways
    """
    giveaways = await giveaway_service.search_giveaways(query, limit=limit)
    giveaway_list = [
        GiveawayResponse.model_validate(g).model_dump()
        for g in giveaways
    ]

    return create_success_response(
        data={
            "giveaways": giveaway_list,
            "count": len(giveaway_list),
            "query": query,
        }
    )


@router.post(
    "/{code}/check-safety",
    response_model=Dict[str, Any],
    summary="Check giveaway safety",
    description="Check if a giveaway is safe to enter (trap detection).",
)
async def check_giveaway_safety(
    code: str,
    giveaway_service: GiveawayServiceDep,
) -> Dict[str, Any]:
    """
    Check if a giveaway is safe to enter.

    Analyzes the giveaway page for warning signs like "don't enter",
    "ban", "fake", etc. that might indicate a trap giveaway.

    Args:
        code: SteamGifts giveaway code

    Returns:
        Success response with safety check results:
            - is_safe: True if giveaway appears safe
            - safety_score: Confidence score (0-100)
            - details: List of found warning words
    """
    try:
        safety = await giveaway_service.check_giveaway_safety(code)
        return create_success_response(data=safety)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Safety check failed: {str(e)}"
        )


@router.post(
    "/{code}/hide-on-steamgifts",
    response_model=Dict[str, Any],
    summary="Hide game on SteamGifts",
    description="Hide all giveaways for this game on SteamGifts.com",
)
async def hide_on_steamgifts(
    code: str,
    giveaway_service: GiveawayServiceDep,
) -> Dict[str, Any]:
    """
    Hide a game on SteamGifts.

    This sends a request to SteamGifts to hide all giveaways for the
    game associated with this giveaway. The game will no longer appear
    in your giveaway lists on SteamGifts.com.

    Args:
        code: SteamGifts giveaway code

    Returns:
        Success response confirming hide

    Raises:
        HTTPException: 400 if hide fails
    """
    success = await giveaway_service.hide_on_steamgifts(code)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to hide giveaway {code} on SteamGifts"
        )

    return create_success_response(
        data={
            "message": "Game hidden on SteamGifts",
            "code": code,
        }
    )


@router.post(
    "/{code}/comment",
    response_model=Dict[str, Any],
    summary="Post comment on giveaway",
    description="Post a comment on a SteamGifts giveaway (e.g., 'Thanks!').",
)
async def post_comment(
    code: str,
    giveaway_service: GiveawayServiceDep,
    comment: str = "Thanks!",
) -> Dict[str, Any]:
    """
    Post a comment on a giveaway.

    This sends a comment to the giveaway page on SteamGifts.com.
    Useful for thanking giveaway creators.

    Args:
        code: SteamGifts giveaway code
        comment: Comment text (default: "Thanks!")

    Returns:
        Success response confirming comment was posted

    Raises:
        HTTPException: 400 if comment fails
    """
    success = await giveaway_service.post_comment(code, comment)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to post comment on giveaway {code}"
        )

    return create_success_response(
        data={
            "message": "Comment posted successfully",
            "code": code,
            "comment": comment,
        }
    )
