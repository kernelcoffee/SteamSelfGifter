"""System API router.

This module provides system-level endpoints for health checks,
system information, and activity logs.
"""

import csv
import json
from io import StringIO
from typing import Dict, Any
from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from api.dependencies import NotificationServiceDep
from api.schemas.common import create_success_response
from core.config import settings


router = APIRouter()


@router.get("/health", response_model=Dict[str, Any])
async def health_check() -> Dict[str, Any]:
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
            "timestamp": datetime.utcnow().isoformat(),
            "version": "0.1.0",
        }
    )


@router.get("/info", response_model=Dict[str, Any])
async def system_info() -> Dict[str, Any]:
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


@router.get("/logs", response_model=Dict[str, Any])
async def get_logs(
    notification_service: NotificationServiceDep,
    limit: int = Query(default=50, ge=1, le=500, description="Number of logs to retrieve"),
    level: str | None = Query(default=None, description="Filter by log level (info, warning, error)"),
    event_type: str | None = Query(default=None, description="Filter by event type (scan, entry, error, config, scheduler)"),
) -> Dict[str, Any]:
    """
    Get recent activity logs.

    Retrieves recent activity logs from the system.

    Args:
        notification_service: Notification service dependency
        limit: Maximum number of logs to retrieve (1-500, default 50)
        level: Optional filter by log level
        event_type: Optional filter by event type

    Returns:
        dict: List of recent logs

    Example Response:
        {
            "success": true,
            "data": {
                "logs": [
                    {
                        "id": 123,
                        "level": "info",
                        "message": "Entered giveaway for Portal 2",
                        "event_type": "entry",
                        "created_at": "2024-01-15T10:30:00"
                    }
                ],
                "count": 1,
                "limit": 50
            }
        }
    """
    # Get activity logs based on filter
    if level:
        activity_logs = await notification_service.get_logs_by_level(
            level=level,
            limit=limit,
        )
    elif event_type:
        activity_logs = await notification_service.get_logs_by_event_type(
            event_type=event_type,
            limit=limit,
        )
    else:
        activity_logs = await notification_service.get_recent_logs(limit=limit)

    # Convert to log format
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
            "count": len(logs),
            "limit": limit,
        }
    )


@router.delete("/logs", response_model=Dict[str, Any])
async def clear_logs(
    notification_service: NotificationServiceDep,
) -> Dict[str, Any]:
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
):
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
        filename = f"logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    else:
        # Generate JSON
        content = json.dumps(logs_data, indent=2)
        media_type = "application/json"
        filename = f"logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
