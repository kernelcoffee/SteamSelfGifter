"""Entries API router for entry history and statistics.

This module provides REST API endpoints for viewing entry history,
filtering entries, and getting entry statistics.
"""

from datetime import date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from api.dependencies import GiveawayServiceDep
from api.schemas.common import create_success_response
from api.schemas.entry import (
    EntryHistoryItem,
    EntryResponse,
    EntryStats,
)

router = APIRouter()


@router.get(
    "/",
    response_model=dict[str, Any],
    summary="List entries",
    description="Get entry history with combinable filters and pagination.",
)
async def list_entries(
    giveaway_service: GiveawayServiceDep,
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Filter by status (success, failed, pending)",
        pattern="^(success|failed|pending)$"
    ),
    entry_type: str | None = Query(
        default=None,
        description="Filter by entry type (manual, auto, wishlist, dlc)",
        pattern="^(manual|auto|wishlist|dlc)$"
    ),
    giveaway_id: int | None = Query(default=None, description="Filter by giveaway ID"),
    from_date: date | None = Query(default=None, description="Only entries on/after this date"),
    to_date: date | None = Query(default=None, description="Only entries on/before this date"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
) -> dict[str, Any]:
    """
    List entries with combinable filters.

    All filters compose (AND). ``count`` in the response is the total number
    of matching rows (not the page size), so clients can paginate.

    Example response:
        {
            "success": true,
            "data": {
                "entries": [...],
                "count": 137,
                "limit": 50,
                "offset": 0
            }
        }
    """
    rows, total = await giveaway_service.entry_repo.search(
        status=status_filter,
        entry_type=entry_type,
        giveaway_id=giveaway_id,
        from_date=datetime.combine(from_date, time.min) if from_date else None,
        # to_date is inclusive: match everything before the next midnight
        to_date=datetime.combine(to_date + timedelta(days=1), time.min) if to_date else None,
        limit=limit,
        offset=offset,
    )

    entry_list = []
    for entry, giveaway in rows:
        entry_data = EntryResponse.model_validate(entry).model_dump()
        if giveaway:
            entry_data["giveaway"] = {
                "id": giveaway.id,
                "code": giveaway.code,
                "url": giveaway.url,
                "game_name": giveaway.game_name,
                "game_id": giveaway.game_id,
                "price": giveaway.price,
                "copies": giveaway.copies,
                "end_time": giveaway.end_time.isoformat() + "Z" if giveaway.end_time else None,
            }
        entry_list.append(entry_data)

    return create_success_response(
        data={
            "entries": entry_list,
            "count": total,
            "limit": limit,
            "offset": offset,
        }
    )


@router.get(
    "/stats",
    response_model=dict[str, Any],
    summary="Get entry statistics",
    description="Get comprehensive statistics about entries.",
)
async def get_entry_stats(
    giveaway_service: GiveawayServiceDep,
) -> dict[str, Any]:
    """
    Get entry statistics.

    Returns:
        Success response with entry statistics
    """
    stats = await giveaway_service.get_entry_stats()

    # Format for response
    response = EntryStats(
        total=stats.get("total", 0),
        successful=stats.get("successful", 0),
        failed=stats.get("failed", 0),
        total_points_spent=stats.get("total_points_spent", 0),
        manual_entries=stats.get("by_type", {}).get("manual", 0),
        auto_entries=stats.get("by_type", {}).get("auto", 0),
        wishlist_entries=stats.get("by_type", {}).get("wishlist", 0),
        success_rate=stats.get("success_rate", 0.0),
    )

    return create_success_response(data=response.model_dump())


@router.get(
    "/recent",
    response_model=dict[str, Any],
    summary="Get recent entries",
    description="Get the most recent entries.",
)
async def get_recent_entries(
    giveaway_service: GiveawayServiceDep,
    limit: int = Query(default=10, ge=1, le=50, description="Maximum results"),
) -> dict[str, Any]:
    """
    Get recent entries.

    Returns:
        Success response with recent entries
    """
    entries = await giveaway_service.entry_repo.get_recent(limit=limit)
    entry_list = [
        EntryResponse.model_validate(e).model_dump()
        for e in entries
    ]

    return create_success_response(
        data={
            "entries": entry_list,
            "count": len(entry_list),
        }
    )


@router.get(
    "/successful",
    response_model=dict[str, Any],
    summary="Get successful entries",
    description="Get all successful entries.",
)
async def get_successful_entries(
    giveaway_service: GiveawayServiceDep,
    limit: int = Query(default=50, ge=1, le=200, description="Maximum results"),
) -> dict[str, Any]:
    """
    Get successful entries.

    Returns:
        Success response with successful entries
    """
    entries = await giveaway_service.entry_repo.get_successful()
    # Apply limit
    entries = entries[:limit]

    entry_list = [
        EntryResponse.model_validate(e).model_dump()
        for e in entries
    ]

    return create_success_response(
        data={
            "entries": entry_list,
            "count": len(entry_list),
        }
    )


@router.get(
    "/failed",
    response_model=dict[str, Any],
    summary="Get failed entries",
    description="Get all failed entries for debugging.",
)
async def get_failed_entries(
    giveaway_service: GiveawayServiceDep,
    limit: int = Query(default=50, ge=1, le=200, description="Maximum results"),
) -> dict[str, Any]:
    """
    Get failed entries.

    Returns:
        Success response with failed entries including error messages
    """
    entries = await giveaway_service.entry_repo.get_recent_failures(limit=limit)
    entry_list = [
        EntryResponse.model_validate(e).model_dump()
        for e in entries
    ]

    return create_success_response(
        data={
            "entries": entry_list,
            "count": len(entry_list),
        }
    )


@router.get(
    "/history",
    response_model=dict[str, Any],
    summary="Get entry history with giveaway info",
    description="Get entry history with associated giveaway and game information.",
)
async def get_entry_history(
    giveaway_service: GiveawayServiceDep,
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results"),
) -> dict[str, Any]:
    """
    Get entry history with giveaway information.

    Returns:
        Success response with entry history items
    """
    entries = await giveaway_service.entry_repo.get_recent(limit=limit)

    history_items = []
    for entry in entries:
        # Get associated giveaway
        giveaway = await giveaway_service.giveaway_repo.get_by_id(entry.giveaway_id)
        if giveaway:
            item = EntryHistoryItem(
                entry=EntryResponse.model_validate(entry),
                game_name=giveaway.game_name,
                game_id=giveaway.game_id,
                giveaway_code=giveaway.code,
            )
            history_items.append(item.model_dump())

    return create_success_response(
        data={
            "entries": history_items,
            "count": len(history_items),
        }
    )


@router.get(
    "/{entry_id}",
    response_model=dict[str, Any],
    summary="Get entry by ID",
    description="Get a specific entry by its ID.",
)
async def get_entry(
    entry_id: int,
    giveaway_service: GiveawayServiceDep,
) -> dict[str, Any]:
    """
    Get a specific entry by ID.

    Args:
        entry_id: Entry record ID

    Returns:
        Success response with entry details

    Raises:
        HTTPException: 404 if entry not found
    """
    entry = await giveaway_service.entry_repo.get_by_id(entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entry with ID {entry_id} not found"
        )

    return create_success_response(
        data=EntryResponse.model_validate(entry).model_dump()
    )


@router.get(
    "/giveaway/{giveaway_id}",
    response_model=dict[str, Any],
    summary="Get entries for giveaway",
    description="Get all entries for a specific giveaway.",
)
async def get_entries_for_giveaway(
    giveaway_id: int,
    giveaway_service: GiveawayServiceDep,
) -> dict[str, Any]:
    """
    Get entries for a specific giveaway.

    Args:
        giveaway_id: Giveaway ID

    Returns:
        Success response with entries for the giveaway
    """
    entry = await giveaway_service.entry_repo.get_by_giveaway(giveaway_id)

    if entry:
        entry_list = [EntryResponse.model_validate(entry).model_dump()]
    else:
        entry_list = []

    return create_success_response(
        data={
            "entries": entry_list,
            "count": len(entry_list),
            "giveaway_id": giveaway_id,
        }
    )


@router.get(
    "/points/total",
    response_model=dict[str, Any],
    summary="Get total points spent",
    description="Get the total points spent on all entries.",
)
async def get_total_points_spent(
    giveaway_service: GiveawayServiceDep,
) -> dict[str, Any]:
    """
    Get total points spent on entries.

    Returns:
        Success response with total points
    """
    total = await giveaway_service.entry_repo.get_total_points_spent()
    successful = await giveaway_service.entry_repo.get_total_points_by_status("success")

    return create_success_response(
        data={
            "total_points_spent": total,
            "successful_points_spent": successful,
        }
    )
