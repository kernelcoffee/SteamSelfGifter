"""Analytics API router for statistics and reporting.

This module provides REST API endpoints for analytics and statistics,
aggregating data from giveaways, entries, and games.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta, UTC
from fastapi import APIRouter, Query

from api.schemas.common import create_success_response
from api.dependencies import GiveawayServiceDep, GameServiceDep, SchedulerServiceDep, SettingsServiceDep

router = APIRouter()


@router.get(
    "/overview",
    response_model=Dict[str, Any],
    summary="Get analytics overview",
    description="Get a comprehensive overview of all statistics.",
)
async def get_analytics_overview(
    giveaway_service: GiveawayServiceDep,
) -> Dict[str, Any]:
    """
    Get analytics overview.

    Returns:
        Success response with comprehensive statistics
    """
    # Get giveaway stats
    giveaway_stats = await giveaway_service.get_giveaway_stats()

    # Get entry stats
    entry_stats = await giveaway_service.get_entry_stats()

    return create_success_response(
        data={
            "giveaways": {
                "total": giveaway_stats.get("total", 0),
                "active": giveaway_stats.get("active", 0),
                "entered": giveaway_stats.get("entered", 0),
                "hidden": giveaway_stats.get("hidden", 0),
            },
            "entries": {
                "total": entry_stats.get("total", 0),
                "successful": entry_stats.get("successful", 0),
                "failed": entry_stats.get("failed", 0),
                "success_rate": entry_stats.get("success_rate", 0.0),
                "total_points_spent": entry_stats.get("total_points_spent", 0),
            },
            "by_type": entry_stats.get("by_type", {}),
        }
    )


def _get_period_start(period: Optional[str]) -> Optional[datetime]:
    """Convert period string to start datetime."""
    if not period or period == "all":
        return None

    now = datetime.now(UTC)
    if period == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        return now - timedelta(days=7)
    elif period == "month":
        return now - timedelta(days=30)
    elif period == "year":
        return now - timedelta(days=365)
    return None


@router.get(
    "/entries/summary",
    response_model=Dict[str, Any],
    summary="Get entry summary",
    description="Get summary statistics about entries.",
)
async def get_entry_summary(
    giveaway_service: GiveawayServiceDep,
    period: Optional[str] = Query(
        default=None,
        description="Time period: day, week, month, year, or all",
    ),
) -> Dict[str, Any]:
    """
    Get entry summary statistics.

    Args:
        period: Time period to filter by (day, week, month, year, all)

    Returns:
        Success response with entry summary
    """
    since = _get_period_start(period)

    if since:
        entry_stats = await giveaway_service.entry_repo.get_stats_since(since)
    else:
        entry_stats = await giveaway_service.get_entry_stats()

    # Calculate average points per entry
    total = entry_stats.get("total", 0)
    total_points = entry_stats.get("total_points_spent", 0)
    avg_points = total_points / total if total > 0 else 0

    return create_success_response(
        data={
            "total_entries": entry_stats.get("total", 0),
            "successful_entries": entry_stats.get("successful", 0),
            "failed_entries": entry_stats.get("failed", 0),
            "success_rate": entry_stats.get("success_rate", 0.0),
            "total_points_spent": total_points,
            "average_points_per_entry": avg_points,
            "by_type": entry_stats.get("by_type", {}),
        }
    )


@router.get(
    "/giveaways/summary",
    response_model=Dict[str, Any],
    summary="Get giveaway summary",
    description="Get summary statistics about giveaways.",
)
async def get_giveaway_summary(
    giveaway_service: GiveawayServiceDep,
    period: Optional[str] = Query(
        default=None,
        description="Time period: day, week, month, year, or all",
    ),
) -> Dict[str, Any]:
    """
    Get giveaway summary statistics.

    Args:
        period: Time period to filter by (day, week, month, year, all)

    Returns:
        Success response with giveaway summary
    """
    since = _get_period_start(period)

    if since:
        giveaway_stats = await giveaway_service.giveaway_repo.get_stats_since(since)
    else:
        giveaway_stats = await giveaway_service.get_giveaway_stats()

    # Get expiring soon count
    expiring_soon = await giveaway_service.get_expiring_soon(hours=24, limit=None)
    expiring_count = len(expiring_soon) if expiring_soon else 0

    return create_success_response(
        data={
            "total_giveaways": giveaway_stats.get("total", 0),
            "active_giveaways": giveaway_stats.get("active", 0),
            "entered_giveaways": giveaway_stats.get("entered", 0),
            "hidden_giveaways": giveaway_stats.get("hidden", 0),
            "expiring_24h": expiring_count,
            "wins": giveaway_stats.get("wins", 0),
            "win_rate": giveaway_stats.get("win_rate", 0.0),
        }
    )


@router.get(
    "/games/summary",
    response_model=Dict[str, Any],
    summary="Get game cache summary",
    description="Get summary statistics about cached game data.",
)
async def get_game_summary(
    game_service: GameServiceDep,
) -> Dict[str, Any]:
    """
    Get game cache summary statistics.

    Returns:
        Success response with game cache summary
    """
    cache_stats = await game_service.get_game_cache_stats()
    by_type = cache_stats.get("by_type", {})

    return create_success_response(
        data={
            "total_games": cache_stats.get("total", 0),
            "games": by_type.get("game", 0),
            "dlc": by_type.get("dlc", 0),
            "bundles": by_type.get("bundle", 0),
            "stale_games": cache_stats.get("stale_count", 0),
        }
    )


@router.get(
    "/scheduler/summary",
    response_model=Dict[str, Any],
    summary="Get scheduler summary",
    description="Get summary statistics about scheduler operations.",
)
async def get_scheduler_summary(
    scheduler_service: SchedulerServiceDep,
) -> Dict[str, Any]:
    """
    Get scheduler summary statistics.

    Returns:
        Success response with scheduler summary
    """
    stats = await scheduler_service.get_scheduler_stats()

    return create_success_response(
        data={
            "total_scans": stats.get("total_scans", 0),
            "total_entries": stats.get("total_entries", 0),
            "total_errors": stats.get("total_errors", 0),
            "last_scan_at": stats.get("last_scan_at"),
            "next_scan_at": stats.get("next_scan_at"),
        }
    )


@router.get(
    "/points",
    response_model=Dict[str, Any],
    summary="Get points analytics",
    description="Get detailed analytics about points spent.",
)
async def get_points_analytics(
    giveaway_service: GiveawayServiceDep,
) -> Dict[str, Any]:
    """
    Get points analytics.

    Returns:
        Success response with points analytics
    """
    # Get total points spent
    total_spent = await giveaway_service.entry_repo.get_total_points_spent()
    successful_spent = await giveaway_service.entry_repo.get_total_points_by_status("success")
    failed_spent = await giveaway_service.entry_repo.get_total_points_by_status("failed")

    # Get average
    avg_points = await giveaway_service.entry_repo.get_average_points_per_entry()

    # Get by type
    entry_stats = await giveaway_service.get_entry_stats()
    by_type = entry_stats.get("by_type", {})

    return create_success_response(
        data={
            "total_points_spent": total_spent or 0,
            "successful_points_spent": successful_spent or 0,
            "failed_points_spent": failed_spent or 0,
            "average_points_per_entry": avg_points or 0,
            "entries_by_type": {
                "manual": by_type.get("manual", 0),
                "auto": by_type.get("auto", 0),
                "wishlist": by_type.get("wishlist", 0),
            },
        }
    )


@router.get(
    "/recent-activity",
    response_model=Dict[str, Any],
    summary="Get recent activity",
    description="Get summary of recent activity including entries and scans.",
)
async def get_recent_activity(
    giveaway_service: GiveawayServiceDep,
    hours: int = Query(default=24, ge=1, le=168, description="Hours to look back"),
) -> Dict[str, Any]:
    """
    Get recent activity summary.

    Args:
        hours: Number of hours to look back

    Returns:
        Success response with recent activity
    """
    since = datetime.now(UTC) - timedelta(hours=hours)

    # Get recent entries
    recent_entries = await giveaway_service.entry_repo.get_entries_since(since, limit=100)

    # Count successful vs failed
    successful = sum(1 for e in recent_entries if e.status == "success")
    failed = sum(1 for e in recent_entries if e.status == "failed")
    points_spent = sum(e.points_spent for e in recent_entries if e.status == "success")

    return create_success_response(
        data={
            "period_hours": hours,
            "entries": {
                "total": len(recent_entries),
                "successful": successful,
                "failed": failed,
                "points_spent": points_spent,
            },
        }
    )


@router.get(
    "/dashboard",
    response_model=Dict[str, Any],
    summary="Get dashboard data",
    description="Get all data needed for the main dashboard in a single request.",
)
async def get_dashboard_data(
    giveaway_service: GiveawayServiceDep,
    scheduler_service: SchedulerServiceDep,
    settings_service: SettingsServiceDep,
) -> Dict[str, Any]:
    """
    Get all dashboard data in a single request.

    This is optimized to reduce the number of API calls needed for the dashboard.

    Returns:
        Success response with all dashboard data including:
        - Session status (configured, valid, username)
        - Current SteamGifts points
        - Entry statistics (total, today's count, success rate)
        - Giveaway counts (active, entered)
        - Scheduler status (running, paused, last_scan, next_scan)
    """
    # Check session status first
    session_result = await settings_service.test_session()
    session_valid = session_result.get("valid", False)
    session_username = session_result.get("username")
    session_error = session_result.get("error")

    # Get settings to check if configured
    settings = await settings_service.get_settings()
    session_configured = bool(settings.phpsessid)

    # Get current points - use from session test if available, otherwise try to fetch
    current_points = session_result.get("points") if session_valid else None

    # Get all stats (these work even without a valid session - they're from DB)
    giveaway_stats = await giveaway_service.get_giveaway_stats()
    entry_stats = await giveaway_service.get_entry_stats()

    # Get wins count
    wins_count = await giveaway_service.get_win_count()

    # Get today's entries (since start of today UTC)
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    today_entries = await giveaway_service.entry_repo.get_entries_since(today_start, limit=None)
    today_count = len(today_entries) if today_entries else 0

    # Get scheduler status
    scheduler_stats = await scheduler_service.get_scheduler_stats()

    # Calculate 30-day stats for meaningful win rate
    # This avoids mixing historical wins with recently tracked entries
    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
    entered_30d = await giveaway_service.giveaway_repo.count_entered_since(thirty_days_ago)
    wins_30d = await giveaway_service.giveaway_repo.count_won_since(thirty_days_ago)
    win_rate_30d = (wins_30d / entered_30d * 100) if entered_30d > 0 else 0.0

    # Get safety stats
    safety_stats = await giveaway_service.giveaway_repo.get_safety_stats()

    return create_success_response(
        data={
            "session": {
                "configured": session_configured,
                "valid": session_valid,
                "username": session_username,
                "error": session_error,
            },
            "points": {
                "current": current_points,
            },
            "entries": {
                "total": entry_stats.get("total", 0),
                "today": today_count,
                "entered_30d": entered_30d,
                "wins_30d": wins_30d,
                "win_rate": win_rate_30d,
            },
            "giveaways": {
                "active": giveaway_stats.get("active", 0),
                "entered": giveaway_stats.get("entered", 0),
                "wins": wins_count,
            },
            "safety": {
                "checked": safety_stats.get("checked", 0),
                "safe": safety_stats.get("safe", 0),
                "unsafe": safety_stats.get("unsafe", 0),
                "unchecked": safety_stats.get("unchecked", 0),
            },
            "scheduler": {
                "running": scheduler_stats.get("running", False),
                "paused": scheduler_stats.get("paused", False),
                "last_scan": scheduler_stats.get("last_scan_at").isoformat() if scheduler_stats.get("last_scan_at") else None,
                "next_scan": scheduler_stats.get("next_scan_at").isoformat() if scheduler_stats.get("next_scan_at") else None,
            },
        }
    )
