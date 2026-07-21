"""Repository for ActivityLog model."""

from datetime import datetime

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.activity_log import ActivityLog


class ActivityLogRepository:
    """
    Repository for ActivityLog data access.

    This repository provides methods for creating and retrieving activity logs.

    Design Notes:
        - Logs are immutable (insert-only, no updates)
        - All queries ordered by created_at desc (newest first)
        - No delete method (logs kept for audit trail)
        - All methods are async

    Usage:
        >>> repo = ActivityLogRepository(session)
        >>> log = await repo.create(level="info", event_type="scan", message="Started scan")
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: SQLAlchemy async session

        Example:
            >>> repo = ActivityLogRepository(session)
        """
        self.session = session

    async def create(
        self,
        level: str,
        event_type: str,
        message: str,
        details: str | None = None,
    ) -> ActivityLog:
        """
        Create a new activity log entry.

        Args:
            level: Log severity ("info", "warning", "error")
            event_type: Event category ("scan", "entry", "error", "config", etc.)
            message: Human-readable log message
            details: Optional JSON-formatted details

        Returns:
            Created ActivityLog object

        Example:
            >>> log = await repo.create(
            ...     level="info",
            ...     event_type="scan",
            ...     message="Found 15 new giveaways",
            ...     details='{"count": 15}'
            ... )
        """
        log = ActivityLog(
            level=level,
            event_type=event_type,
            message=message,
            details=details,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_by_id(self, log_id: int) -> ActivityLog | None:
        """
        Get activity log by ID.

        Args:
            log_id: Log ID

        Returns:
            ActivityLog object if found, None otherwise

        Example:
            >>> log = await repo.get_by_id(123)
        """
        result = await self.session.execute(
            select(ActivityLog).where(ActivityLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def get_recent(self, limit: int = 100) -> list[ActivityLog]:
        """
        Get recent activity logs.

        Args:
            limit: Maximum number of logs to return (default: 100)

        Returns:
            List of ActivityLog objects (newest first)

        Example:
            >>> logs = await repo.get_recent(limit=50)
        """
        result = await self.session.execute(
            select(ActivityLog)
            .order_by(desc(ActivityLog.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_level(self, level: str, limit: int = 100) -> list[ActivityLog]:
        """
        Get activity logs by severity level.

        Args:
            level: Log severity ("info", "warning", "error")
            limit: Maximum number of logs to return (default: 100)

        Returns:
            List of ActivityLog objects matching level (newest first)

        Example:
            >>> errors = await repo.get_by_level("error", limit=20)
        """
        result = await self.session.execute(
            select(ActivityLog)
            .where(ActivityLog.level == level)
            .order_by(desc(ActivityLog.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_event_type(
        self, event_type: str, limit: int = 100
    ) -> list[ActivityLog]:
        """
        Get activity logs by event type.

        Args:
            event_type: Event category ("scan", "entry", "error", "config", etc.)
            limit: Maximum number of logs to return (default: 100)

        Returns:
            List of ActivityLog objects matching event type (newest first)

        Example:
            >>> scan_logs = await repo.get_by_event_type("scan", limit=50)
        """
        result = await self.session.execute(
            select(ActivityLog)
            .where(ActivityLog.event_type == event_type)
            .order_by(desc(ActivityLog.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def search(
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
        Combinable filtered log listing with true total count.

        All filters compose (AND); ``search`` matches the message
        case-insensitively. Returns one page (newest first) plus the total
        number of matching rows for pagination.
        """
        conditions = []
        if level:
            conditions.append(ActivityLog.level == level)
        if event_type:
            conditions.append(ActivityLog.event_type == event_type)
        if search:
            conditions.append(ActivityLog.message.ilike(f"%{search}%"))
        if from_date:
            conditions.append(ActivityLog.created_at >= from_date)
        if to_date:
            conditions.append(ActivityLog.created_at < to_date)

        count_query = select(func.count()).select_from(ActivityLog).where(*conditions)
        total = (await self.session.execute(count_query)).scalar_one()

        page_query = (
            select(ActivityLog)
            .where(*conditions)
            .order_by(desc(ActivityLog.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(page_query)
        return list(result.scalars().all()), total

    async def count_by_level(self, level: str) -> int:
        """
        Count activity logs by severity level.

        Args:
            level: Log severity ("info", "warning", "error")

        Returns:
            Count of logs matching level

        Example:
            >>> error_count = await repo.count_by_level("error")
        """
        result = await self.session.execute(
            select(func.count()).select_from(ActivityLog).where(ActivityLog.level == level)
        )
        return result.scalar_one()

    async def delete_older_than(self, cutoff: datetime) -> int:
        """
        Delete logs created before ``cutoff`` (retention pruning).

        Returns:
            Number of logs deleted

        Note:
            Does NOT commit; the caller must call session.commit().
        """
        result = await self.session.execute(
            delete(ActivityLog).where(ActivityLog.created_at < cutoff)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def get_all(self) -> list[ActivityLog]:
        """
        Get all activity logs.

        Returns:
            List of all ActivityLog objects (newest first)

        Example:
            >>> all_logs = await repo.get_all()
        """
        result = await self.session.execute(
            select(ActivityLog).order_by(desc(ActivityLog.created_at))
        )
        return list(result.scalars().all())

    async def delete_all(self) -> int:
        """
        Delete all activity logs.

        Returns:
            Number of logs deleted

        Note:
            This method does NOT commit the transaction. The caller must
            call session.commit() to persist changes to the database.

        Example:
            >>> deleted_count = await repo.delete_all()
            >>> await session.commit()
        """
        result = await self.session.execute(delete(ActivityLog))
        # execute() is typed as Result, but DELETE always yields a CursorResult.
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def count(self) -> int:
        """
        Count total activity logs.

        Returns:
            Total count of logs

        Example:
            >>> total = await repo.count()
        """
        result = await self.session.execute(
            select(func.count()).select_from(ActivityLog)
        )
        return result.scalar() or 0
