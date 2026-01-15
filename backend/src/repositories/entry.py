"""Entry repository with giveaway entry tracking queries.

This module provides a specialized repository for the Entry model with
methods for tracking entry history, calculating statistics, and analyzing
entry performance.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.entry import Entry
from repositories.base import BaseRepository


class EntryRepository(BaseRepository[Entry]):
    """
    Repository for Entry model with entry tracking queries.

    This repository extends BaseRepository to provide specialized methods
    for working with giveaway entry data, including success rate calculation,
    recent entries, and statistical analysis.

    Design Notes:
        - Entry stores all entry attempts (including failures) for analytics
        - is_successful, is_failed, is_pending are computed properties
        - Foreign key to Giveaway is indexed for fast lookups
        - One entry per giveaway (unique constraint)

    Usage:
        >>> async with AsyncSessionLocal() as session:
        ...     repo = EntryRepository(session)
        ...     recent = await repo.get_recent(limit=10)
        ...     stats = await repo.get_stats()
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize EntryRepository with database session.

        Args:
            session: The async database session

        Example:
            >>> repo = EntryRepository(session)
        """
        super().__init__(Entry, session)

    async def get_by_giveaway(self, giveaway_id: int) -> Optional[Entry]:
        """
        Get entry for a specific giveaway.

        Args:
            giveaway_id: Giveaway ID to look up

        Returns:
            Entry if exists, None otherwise

        Example:
            >>> entry = await repo.get_by_giveaway(123)
            >>> entry.status
            'success'
        """
        query = select(self.model).where(self.model.giveaway_id == giveaway_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_recent(
        self, limit: Optional[int] = 20, offset: Optional[int] = None
    ) -> List[Entry]:
        """
        Get recent entries ordered by creation time (most recent first).

        Args:
            limit: Maximum number to return (default: 20)
            offset: Number to skip (for pagination)

        Returns:
            List of recent entries

        Example:
            >>> # Get last 10 entries
            >>> recent = await repo.get_recent(limit=10)
        """
        query = select(self.model).order_by(self.model.created_at.desc())

        if limit:
            query = query.limit(limit)
        if offset:
            query = query.offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_status(
        self, status: str, limit: Optional[int] = None
    ) -> List[Entry]:
        """
        Get entries by status.

        Args:
            status: Status to filter by ("success", "failed", "pending")
            limit: Maximum number to return

        Returns:
            List of entries with specified status

        Example:
            >>> failed = await repo.get_by_status("failed")
            >>> len(failed)
            5
        """
        query = (
            select(self.model)
            .where(self.model.status == status)
            .order_by(self.model.created_at.desc())
        )

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_successful(self, limit: Optional[int] = None) -> List[Entry]:
        """
        Get all successful entries.

        Args:
            limit: Maximum number to return

        Returns:
            List of successful entries

        Example:
            >>> successful = await repo.get_successful(limit=50)
        """
        return await self.get_by_status("success", limit)

    async def get_failed(self, limit: Optional[int] = None) -> List[Entry]:
        """
        Get all failed entries.

        Args:
            limit: Maximum number to return

        Returns:
            List of failed entries

        Example:
            >>> failed = await repo.get_failed()
        """
        return await self.get_by_status("failed", limit)

    async def get_pending(self, limit: Optional[int] = None) -> List[Entry]:
        """
        Get all pending entries.

        Args:
            limit: Maximum number to return

        Returns:
            List of pending entries

        Example:
            >>> pending = await repo.get_pending()
        """
        return await self.get_by_status("pending", limit)

    async def get_by_entry_type(
        self, entry_type: str, limit: Optional[int] = None
    ) -> List[Entry]:
        """
        Get entries by type.

        Args:
            entry_type: Type to filter by ("manual", "auto", "wishlist")
            limit: Maximum number to return

        Returns:
            List of entries with specified type

        Example:
            >>> manual_entries = await repo.get_by_entry_type("manual")
        """
        query = (
            select(self.model)
            .where(self.model.entry_type == entry_type)
            .order_by(self.model.created_at.desc())
        )

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_in_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: Optional[int] = None,
    ) -> List[Entry]:
        """
        Get entries within a date range.

        Args:
            start_date: Start of range (inclusive)
            end_date: End of range (inclusive)
            limit: Maximum number to return

        Returns:
            List of entries in date range

        Example:
            >>> # Get entries from last 7 days
            >>> start = datetime.utcnow() - timedelta(days=7)
            >>> end = datetime.utcnow()
            >>> recent = await repo.get_in_date_range(start, end)
        """
        query = (
            select(self.model)
            .where(
                and_(
                    self.model.created_at >= start_date,
                    self.model.created_at <= end_date,
                )
            )
            .order_by(self.model.created_at.desc())
        )

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_by_status(self, status: str) -> int:
        """
        Count entries with specific status.

        Args:
            status: Status to count ("success", "failed", "pending")

        Returns:
            Number of entries with status

        Example:
            >>> success_count = await repo.count_by_status("success")
            >>> print(f"Successful entries: {success_count}")
        """
        query = select(func.count()).where(self.model.status == status)
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def count_successful(self) -> int:
        """
        Count successful entries.

        Returns:
            Number of successful entries

        Example:
            >>> count = await repo.count_successful()
        """
        return await self.count_by_status("success")

    async def count_failed(self) -> int:
        """
        Count failed entries.

        Returns:
            Number of failed entries

        Example:
            >>> count = await repo.count_failed()
        """
        return await self.count_by_status("failed")

    async def count_by_type(self, entry_type: str) -> int:
        """
        Count entries by type.

        Args:
            entry_type: Entry type to count ("manual", "auto", "wishlist")

        Returns:
            Number of entries of that type

        Example:
            >>> auto_count = await repo.count_by_type("auto")
        """
        query = select(func.count()).where(self.model.entry_type == entry_type)
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_total_points_spent(self) -> int:
        """
        Calculate total points spent across all entries.

        Returns:
            Total points spent (sum of all entries)

        Example:
            >>> total = await repo.get_total_points_spent()
            >>> print(f"Total points spent: {total}")
        """
        query = select(func.sum(self.model.points_spent))
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_total_points_by_status(self, status: str) -> int:
        """
        Calculate total points spent on entries with specific status.

        Args:
            status: Status to filter by

        Returns:
            Total points for that status

        Example:
            >>> successful_points = await repo.get_total_points_by_status("success")
        """
        query = select(func.sum(self.model.points_spent)).where(
            self.model.status == status
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_success_rate(self) -> float:
        """
        Calculate overall success rate (percentage).

        Returns:
            Success rate as percentage (0-100), or 0 if no entries

        Example:
            >>> rate = await repo.get_success_rate()
            >>> print(f"Success rate: {rate:.1f}%")
        """
        total = await self.count()
        if total == 0:
            return 0.0

        successful = await self.count_successful()
        return (successful / total) * 100

    async def get_stats(self) -> dict:
        """
        Get comprehensive entry statistics.

        Returns:
            Dictionary with statistics:
                - total: Total entries
                - successful: Successful entries
                - failed: Failed entries
                - pending: Pending entries
                - success_rate: Success rate percentage
                - total_points_spent: Total points across all entries
                - points_on_success: Points spent on successful entries
                - points_on_failures: Points spent on failed entries
                - by_type: Breakdown by entry type

        Example:
            >>> stats = await repo.get_stats()
            >>> print(f"Success rate: {stats['success_rate']:.1f}%")
            >>> print(f"Total spent: {stats['total_points_spent']} points")
        """
        total = await self.count()
        successful = await self.count_successful()
        failed = await self.count_failed()
        pending = await self.count_by_status("pending")

        success_rate = (successful / total * 100) if total > 0 else 0.0

        total_points = await self.get_total_points_spent()
        points_success = await self.get_total_points_by_status("success")
        points_failed = await self.get_total_points_by_status("failed")

        manual_count = await self.count_by_type("manual")
        auto_count = await self.count_by_type("auto")
        wishlist_count = await self.count_by_type("wishlist")

        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "pending": pending,
            "success_rate": success_rate,
            "total_points_spent": total_points,
            "points_on_success": points_success,
            "points_on_failures": points_failed,
            "by_type": {
                "manual": manual_count,
                "auto": auto_count,
                "wishlist": wishlist_count,
            },
        }

    async def get_stats_since(self, since: datetime) -> Dict[str, Any]:
        """
        Get entry statistics since a specific date.

        Args:
            since: Start date for statistics

        Returns:
            Dictionary with statistics filtered by date

        Example:
            >>> from datetime import datetime, timedelta
            >>> week_ago = datetime.utcnow() - timedelta(days=7)
            >>> stats = await repo.get_stats_since(week_ago)
        """
        from sqlalchemy import func, case

        # Single query to get all counts
        query = select(
            func.count().label("total"),
            func.sum(case((self.model.status == "success", 1), else_=0)).label("successful"),
            func.sum(case((self.model.status == "failed", 1), else_=0)).label("failed"),
            func.sum(case((self.model.status == "pending", 1), else_=0)).label("pending"),
            func.sum(case((self.model.status == "success", self.model.points_spent), else_=0)).label("points_success"),
            func.sum(case((self.model.status == "failed", self.model.points_spent), else_=0)).label("points_failed"),
            func.sum(self.model.points_spent).label("total_points"),
            func.sum(case((self.model.entry_type == "manual", 1), else_=0)).label("manual"),
            func.sum(case((self.model.entry_type == "auto", 1), else_=0)).label("auto"),
            func.sum(case((self.model.entry_type == "wishlist", 1), else_=0)).label("wishlist"),
        ).where(self.model.created_at >= since)

        result = await self.session.execute(query)
        row = result.fetchone()

        total = row.total or 0
        successful = row.successful or 0
        failed = row.failed or 0
        pending = row.pending or 0
        success_rate = (successful / total * 100) if total > 0 else 0.0

        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "pending": pending,
            "success_rate": success_rate,
            "total_points_spent": row.total_points or 0,
            "points_on_success": row.points_success or 0,
            "points_on_failures": row.points_failed or 0,
            "by_type": {
                "manual": row.manual or 0,
                "auto": row.auto or 0,
                "wishlist": row.wishlist or 0,
            },
        }

    async def get_recent_failures(self, limit: int = 10) -> List[Entry]:
        """
        Get recent failed entries (for debugging).

        Args:
            limit: Maximum number to return

        Returns:
            List of recent failures with error messages

        Example:
            >>> failures = await repo.get_recent_failures(limit=5)
            >>> for entry in failures:
            ...     print(f"Error: {entry.error_message}")
        """
        query = (
            select(self.model)
            .where(self.model.status == "failed")
            .order_by(self.model.created_at.desc())
            .limit(limit)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_entries_since(
        self, since: datetime, limit: Optional[int] = None
    ) -> List[Entry]:
        """
        Get all entries created after a specific time.

        Args:
            since: Get entries created after this time
            limit: Maximum number to return

        Returns:
            List of entries created after 'since'

        Example:
            >>> # Get entries from last hour
            >>> one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            >>> recent = await repo.get_entries_since(one_hour_ago)
        """
        query = (
            select(self.model)
            .where(self.model.created_at >= since)
            .order_by(self.model.created_at.desc())
        )

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def has_entry_for_giveaway(self, giveaway_id: int) -> bool:
        """
        Check if an entry exists for a giveaway.

        Args:
            giveaway_id: Giveaway ID to check

        Returns:
            True if entry exists, False otherwise

        Example:
            >>> if await repo.has_entry_for_giveaway(123):
            ...     print("Already entered!")
        """
        entry = await self.get_by_giveaway(giveaway_id)
        return entry is not None

    async def get_average_points_per_entry(self) -> float:
        """
        Calculate average points spent per entry.

        Returns:
            Average points, or 0 if no entries

        Example:
            >>> avg = await repo.get_average_points_per_entry()
            >>> print(f"Average: {avg:.1f} points/entry")
        """
        total_points = await self.get_total_points_spent()
        total_entries = await self.count()

        if total_entries == 0:
            return 0.0

        return total_points / total_entries
