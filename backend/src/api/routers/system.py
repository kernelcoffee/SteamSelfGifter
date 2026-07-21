"""System API router.

This module provides system-level endpoints for health checks,
system information, and activity logs.
"""

import csv
import json
from datetime import date, datetime, time, timedelta
from io import StringIO
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from api.dependencies import NotificationServiceDep
from api.schemas.common import create_success_response
from core.config import settings
from core.time import utcnow

router = APIRouter()


@router.get("/health", response_model=dict[str, Any])
async def health_check() -> dict[str, Any]:
    """
    Health check endpoint.

    Returns basic health status of the application.

    Returns:
        dict: Health status with timestamp

    Example Response:
        {
            "success": true,
            "data": {
                "status": "healthy",
                "timestamp": "2024-01-15T10:30:00.000000",
                "version": "0.1.0"
            }
        }
    """
    return create_success_response(
        data={
            "status": "healthy",
            "timestamp": utcnow().isoformat(),
            "version": "0.1.0",
        }
    )


@router.get("/info", response_model=dict[str, Any])
async def system_info() -> dict[str, Any]:
    """
    Get system information.

    Returns application configuration and environment details.

    Returns:
        dict: System information

    Example Response:
        {
            "success": true,
            "data": {
                "app_name": "SteamSelfGifter",
                "version": "0.1.0",
                "debug_mode": false,
                "database_url": "sqlite+aiosqlite:///./data/steamselfgifter.db"
            }
        }
    """
    return create_success_response(
        data={
            "app_name": "SteamSelfGifter",
            "version": "0.1.0",
            "debug_mode": settings.debug,
            "database_url": settings.database_url,
        }
    )


@router.get("/logs", response_model=dict[str, Any])
async def get_logs(
    notification_service: NotificationServiceDep,
    limit: int = Query(default=50, ge=1, le=500, description="Number of logs to retrieve"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    level: str | None = Query(default=None, description="Filter by log level (info, warning, error)"),
    event_type: str | None = Query(
        default=None, description="Filter by event type (scan, entry, error, config, scheduler, win)"
    ),
    search: str | None = Query(default=None, description="Case-insensitive message search"),
    from_date: date | None = Query(default=None, description="Only logs on/after this date"),
    to_date: date | None = Query(default=None, description="Only logs on/before this date"),
) -> dict[str, Any]:
    """
    Get activity logs with combinable filters and pagination.

    All filters compose (AND); ``count`` is the total number of matching
    rows, not the page size.

    Example Response:
        {
            "success": true,
            "data": {
                "logs": [
                    {
                        "id": 123,
                        "level": "info",
                        "message": "Scan completed",
                        "event_type": "scan",
                        "created_at": "2024-01-15T10:30:00"
                    }
                ],
                "count": 412,
                "limit": 50,
                "offset": 0
            }
        }
    """
    activity_logs, total = await notification_service.search_logs(
        level=level,
        event_type=event_type,
        search=search,
        from_date=datetime.combine(from_date, time.min) if from_date else None,
        to_date=datetime.combine(to_date + timedelta(days=1), time.min) if to_date else None,
        limit=limit,
        offset=offset,
    )

    logs = [
        {
            "id": log.id,
            "level": log.level,
            "event_type": log.event_type,
            "message": log.message,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in activity_logs
    ]

    return create_success_response(
        data={
            "logs": logs,
            "count": total,
            "limit": limit,
            "offset": offset,
        }
    )


@router.delete("/logs", response_model=dict[str, Any])
async def clear_logs(
    notification_service: NotificationServiceDep,
) -> dict[str, Any]:
    """
    Clear all activity logs.

    Deletes all activity logs from the database.

    Returns:
        dict: Number of logs deleted

    Example Response:
        {
            "success": true,
            "data": {
                "deleted": 150
            }
        }
    """
    deleted_count = await notification_service.clear_all_logs()

    return create_success_response(
        data={
            "deleted": deleted_count,
        }
    )


@router.get("/logs/export")
async def export_logs(
    notification_service: NotificationServiceDep,
    format: str = Query(default="json", description="Export format (json or csv)"),
) -> StreamingResponse:
    """
    Export all activity logs.

    Returns all logs as a downloadable file in JSON or CSV format.

    Args:
        format: Export format - "json" or "csv"

    Returns:
        StreamingResponse: File download
    """
    activity_logs = await notification_service.get_all_logs()

    # Convert to list of dicts
    logs_data = [
        {
            "id": log.id,
            "level": log.level,
            "event_type": log.event_type,
            "message": log.message,
            "details": log.details,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in activity_logs
    ]

    if format == "csv":
        # Generate CSV
        output = StringIO()
        if logs_data:
            writer = csv.DictWriter(output, fieldnames=logs_data[0].keys())
            writer.writeheader()
            writer.writerows(logs_data)
        content = output.getvalue()
        media_type = "text/csv"
        filename = f"logs_{utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    else:
        # Generate JSON
        content = json.dumps(logs_data, indent=2)
        media_type = "application/json"
        filename = f"logs_{utcnow().strftime('%Y%m%d_%H%M%S')}.json"

    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
