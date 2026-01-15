"""Scheduler state and statistics model."""

from datetime import datetime
from sqlalchemy import Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class SchedulerState(Base, TimestampMixin):
    """
    Scheduler state, timing, and statistics tracking (singleton pattern with id=1).

    This model stores persistent state and metrics for the automation scheduler.
    Only one instance should exist in the database (singleton pattern).

    Attributes:
        id: Primary key, always 1 (singleton)

        Timing Information:
            last_scan_at: When last scan completed (UTC)
            next_scan_at: When next scan is scheduled (UTC)

        Statistics:
            total_scans: Total number of scans completed
            total_entries: Total number of giveaways entered
            total_errors: Total number of errors encountered

        Metadata:
            created_at: When state was first created (from TimestampMixin)
            updated_at: Last time state was updated (from TimestampMixin)

        Computed Properties:
            has_run: True if last_scan_at is not None
            time_since_last_scan: Seconds since last scan
            time_until_next_scan: Seconds until next scan

    Design Notes:
        - Runtime state (is_running, is_paused) NOT stored (computed from APScheduler)
        - automation_enabled stored in Settings model (user preference)
        - This model only stores persistent metrics and timing
        - Singleton pattern ensures only one state record exists

    Example:
        >>> state = SchedulerState(id=1)
        >>> state.total_scans = 100
        >>> state.total_entries = 250
        >>> state.last_scan_at = datetime.utcnow()
        >>> state.has_run
        True
    """

    __tablename__ = "scheduler_state"

    # ==================== Primary Key ====================
    # Singleton - always id=1
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        default=1,
        comment="Singleton ID (always 1)",
    )

    # ==================== Timing Information ====================
    last_scan_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="When last scan completed (UTC)",
    )
    next_scan_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="When next scan is scheduled (UTC)",
    )

    # ==================== Statistics/Metrics ====================
    total_scans: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Total scans completed",
    )
    total_entries: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Total giveaways entered",
    )
    total_errors: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Total errors encountered",
    )

    # NOTE: Runtime state (is_running, is_paused) computed from APScheduler, not stored
    # NOTE: automation_enabled stored in Settings model (user preference)

    def __repr__(self) -> str:
        """String representation of SchedulerState."""
        return (
            f"<SchedulerState(id={self.id}, scans={self.total_scans}, "
            f"entries={self.total_entries})>"
        )

    @property
    def has_run(self) -> bool:
        """
        Check if scheduler has ever run.

        Returns:
            True if last_scan_at is set, False otherwise.
        """
        return self.last_scan_at is not None

    @property
    def time_since_last_scan(self) -> int | None:
        """
        Get seconds since last scan.

        Returns:
            Number of seconds since last scan, or None if never ran.

        Example:
            >>> state.last_scan_at = datetime.utcnow() - timedelta(minutes=5)
            >>> state.time_since_last_scan
            300  # 5 minutes in seconds
        """
        if not self.last_scan_at:
            return None
        return int((datetime.utcnow() - self.last_scan_at).total_seconds())

    @property
    def time_until_next_scan(self) -> int | None:
        """
        Get seconds until next scan.

        Returns:
            Number of seconds until next scan (minimum 0), or None if not scheduled.

        Note:
            Returns 0 if next scan time has already passed (overdue).
        """
        if not self.next_scan_at:
            return None
        remaining = int((self.next_scan_at - datetime.utcnow()).total_seconds())
        return max(0, remaining)  # Don't return negative values
