"""Notification service with event broadcasting and activity logging.

This module provides the service layer for real-time notifications and
activity logging, coordinating between the ActivityLog repository and
WebSocket connection management.
"""

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.time import utcnow
from models.activity_log import ActivityLog
from repositories.activity_log import ActivityLogRepository


class NotificationService:
    """
    Service for notifications and activity logging.

    This service provides:
    - Activity logging to database
    - Event data preparation for WebSocket broadcasting
    - Recent log retrieval for UI

    Design Notes:
        - Service layer handles business logic for notifications
        - ActivityLog repository handles database operations
        - WebSocket connection management handled by API layer (FastAPI)
        - Events prepared as dictionaries for WebSocket serialization
        - All methods are async

    WebSocket Integration:
        The API layer (FastAPI WebSocket endpoint) will:
        1. Call broadcast_event() to prepare event data
        2. Send the event to all connected WebSocket clients
        3. This service doesn't manage connections directly

    Usage:
        >>> async with AsyncSessionLocal() as session:
        ...     service = NotificationService(session)
        ...     # Log activity
        ...     await service.log_activity("info", "scan", "Found 15 giveaways")
        ...     # Prepare event for broadcasting
        ...     event = await service.broadcast_event("scan_complete", {"count": 15})
        ...     # API layer would then send 'event' via WebSocket
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize NotificationService.

        Args:
            session: Database session

        Example:
            >>> service = NotificationService(session)
        """
        self.session = session
        self.repo = ActivityLogRepository(session)

    async def log_activity(
        self,
        level: str,
        event_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> ActivityLog:
        """
        Log an activity event to database.

        This creates a permanent log entry for the activity feed.

        Args:
            level: Log severity - "info", "warning", or "error"
            event_type: Event category - "scan", "entry", "error", "config", etc.
            message: Human-readable log message
            details: Optional dictionary of additional details (serialized to JSON)

        Returns:
            Created ActivityLog object

        Raises:
            ValueError: If level is not valid

        Example:
            >>> log = await service.log_activity(
            ...     level="info",
            ...     event_type="scan",
            ...     message="Found 15 new giveaways",
            ...     details={"count": 15, "page": 1}
            ... )
        """
        # Validate level
        valid_levels = {"info", "warning", "error"}
        if level not in valid_levels:
            raise ValueError(f"Invalid log level: {level}. Must be one of {valid_levels}")

        # Serialize details to JSON string if provided
        details_json = None
        if details:
            details_json = json.dumps(details)

        log = await self.repo.create(
            level=level,
            event_type=event_type,
            message=message,
            details=details_json,
        )
        await self.session.commit()

        return log

    async def broadcast_event(
        self,
        event_type: str,
        data: dict[str, Any],
        log_activity: bool = False,
        log_level: str = "info",
        log_message: str | None = None,
    ) -> dict[str, Any]:
        """
        Prepare an event for WebSocket broadcasting.

        This creates a standardized event structure that can be sent
        via WebSocket to connected clients. Optionally logs the event
        to the activity log.

        Args:
            event_type: Event type - "scan_complete", "entry_success", etc.
            data: Event payload data
            log_activity: Whether to also log this event to ActivityLog
            log_level: Log level if logging ("info", "warning", "error")
            log_message: Custom log message if logging (default: uses event_type)

        Returns:
            Event dictionary ready for WebSocket broadcasting:
                {
                    "type": event_type,
                    "data": data,
                    "timestamp": ISO timestamp
                }

        Example:
            >>> event = await service.broadcast_event(
            ...     event_type="scan_complete",
            ...     data={"new": 5, "updated": 3},
            ...     log_activity=True,
            ...     log_message="Scan completed: 5 new, 3 updated"
            ... )
            >>> # API layer would then broadcast 'event' via WebSocket
        """

        # Prepare event structure
        event = {
            "type": event_type,
            "data": data,
            "timestamp": utcnow().isoformat(),
        }

        # Optionally log to activity log
        if log_activity:
            message = log_message or f"Event: {event_type}"
            await self.log_activity(
                level=log_level,
                event_type=event_type,
                message=message,
                details=data,
            )

        return event

    async def get_recent_logs(self, limit: int = 100) -> list[ActivityLog]:
        """
        Get recent activity logs.

        Args:
            limit: Maximum number of logs to return (default: 100)

        Returns:
            List of ActivityLog objects (newest first)

        Example:
            >>> logs = await service.get_recent_logs(limit=50)
            >>> for log in logs:
            ...     print(f"{log.level}: {log.message}")
        """
        return await self.repo.get_recent(limit=limit)

    async def get_logs_by_level(
        self, level: str, limit: int = 100
    ) -> list[ActivityLog]:
        """
        Get activity logs filtered by severity level.

        Args:
            level: Log severity - "info", "warning", or "error"
            limit: Maximum number of logs to return (default: 100)

        Returns:
            List of ActivityLog objects matching level (newest first)

        Example:
            >>> errors = await service.get_logs_by_level("error", limit=20)
        """
        return await self.repo.get_by_level(level=level, limit=limit)

    async def get_logs_by_event_type(
        self, event_type: str, limit: int = 100
    ) -> list[ActivityLog]:
        """
        Get activity logs filtered by event type.

        Args:
            event_type: Event category - "scan", "entry", "error", "config", etc.
            limit: Maximum number of logs to return (default: 100)

        Returns:
            List of ActivityLog objects matching event type (newest first)

        Example:
            >>> scan_logs = await service.get_logs_by_event_type("scan", limit=50)
        """
        return await self.repo.get_by_event_type(event_type=event_type, limit=limit)

    async def search_logs(
        self,
        *,
        level: str | None = None,
        event_type: str | None = None,
        search: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ActivityLog], int]:
        """
        Combinable filtered log listing with total count (see repo.search).

        Example:
            >>> logs, total = await service.search_logs(level="error", search="scan")
        """
        return await self.repo.search(
            level=level,
            event_type=event_type,
            search=search,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
        )

    async def prune_old_logs(self, retention_days: int) -> int:
        """
        Delete logs older than ``retention_days`` days.

        Args:
            retention_days: Age cutoff in days; values <= 0 disable pruning

        Returns:
            Number of logs deleted

        Example:
            >>> deleted = await service.prune_old_logs(30)
        """
        if retention_days <= 0:
            return 0
        cutoff = utcnow() - timedelta(days=retention_days)
        deleted = await self.repo.delete_older_than(cutoff)
        if deleted:
            await self.session.commit()
        return deleted

    async def get_error_count(self) -> int:
        """
        Get count of error-level logs.

        Returns:
            Number of error logs

        Example:
            >>> error_count = await service.get_error_count()
            >>> if error_count > 0:
            ...     print(f"Warning: {error_count} errors logged")
        """
        return await self.repo.count_by_level("error")

    async def get_warning_count(self) -> int:
        """
        Get count of warning-level logs.

        Returns:
            Number of warning logs

        Example:
            >>> warning_count = await service.get_warning_count()
        """
        return await self.repo.count_by_level("warning")

    async def log_scan_start(self, pages: int) -> ActivityLog:
        """
        Convenience method to log scan start.

        Args:
            pages: Number of pages to scan

        Returns:
            Created ActivityLog object

        Example:
            >>> await service.log_scan_start(pages=3)
        """
        return await self.log_activity(
            level="info",
            event_type="scan",
            message=f"Starting giveaway scan ({pages} pages)",
            details={"pages": pages},
        )

    async def log_scan_complete(
        self, new_count: int, updated_count: int
    ) -> ActivityLog:
        """
        Convenience method to log scan completion.

        Args:
            new_count: Number of new giveaways found
            updated_count: Number of giveaways updated

        Returns:
            Created ActivityLog object

        Example:
            >>> await service.log_scan_complete(new_count=5, updated_count=3)
        """
        return await self.log_activity(
            level="info",
            event_type="scan",
            message=f"Scan complete: {new_count} new, {updated_count} updated",
            details={"new": new_count, "updated": updated_count},
        )

    # Entry attempts are NOT logged here: they are first-class Entry rows
    # (the History page), so mirroring them into the activity log would
    # duplicate every entry event. The activity log carries system events
    # only (scan, scheduler, config, win, error).

    async def log_error(self, error_type: str, message: str, details: dict[str, Any] | None = None) -> ActivityLog:
        """
        Convenience method to log errors.

        Args:
            error_type: Type of error
            message: Error message
            details: Optional error details

        Returns:
            Created ActivityLog object

        Example:
            >>> await service.log_error("api", "SteamGifts API timeout", {"url": "..."})
        """
        return await self.log_activity(
            level="error",
            event_type="error",
            message=f"[{error_type}] {message}",
            details=details,
        )

    async def clear_all_logs(self) -> int:
        """
        Clear all activity logs.

        Returns:
            Number of logs deleted

        Example:
            >>> deleted = await service.clear_all_logs()
            >>> print(f"Deleted {deleted} logs")
        """
        deleted = await self.repo.delete_all()
        await self.session.commit()
        return deleted

    async def get_all_logs(self) -> list[ActivityLog]:
        """
        Get all activity logs for export.

        Returns:
            List of all ActivityLog objects (newest first)

        Example:
            >>> all_logs = await service.get_all_logs()
        """
        return await self.repo.get_all()

    async def get_logs_count(self) -> int:
        """
        Get total count of logs.

        Returns:
            Total count of logs

        Example:
            >>> count = await service.get_logs_count()
        """
        return await self.repo.count()
