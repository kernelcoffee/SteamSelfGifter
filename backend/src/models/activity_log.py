"""Activity and event logging model."""

from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class ActivityLog(Base):
    """
    Application activity and event logging for UI display.

    This model stores application events and activities for display in the
    web UI, providing users with visibility into automation actions and errors.

    Attributes:
        id: Auto-increment primary key

        Log Metadata:
            level: Log severity - "info", "warning", "error" (indexed)
            event_type: Event category - "scan", "entry", "error", "config", etc.

        Log Content:
            message: Human-readable log message
            details: Additional JSON-formatted details (optional)

        Timestamp:
            created_at: When log was created (UTC, indexed for chronological queries)

        Computed Properties:
            is_info: True if level == "info"
            is_warning: True if level == "warning"
            is_error: True if level == "error"

    Log Levels:
        - "info": Informational messages (scans, entries, etc.)
        - "warning": Warning messages (rate limits, skipped entries, etc.)
        - "error": Error messages (failures, exceptions, etc.)

    Event Types:
        - "scan": Giveaway scanning events
        - "entry": Giveaway entry events
        - "error": Error events
        - "config": Configuration change events
        - "scheduler": Scheduler lifecycle events

    Design Notes:
        - No updated_at field (logs are immutable)
        - Indexed on level and created_at for fast filtering/sorting
        - details stored as JSON string for flexibility
        - Used for UI activity feed, not application logging

    Example:
        >>> log = ActivityLog(
        ...     level="info",
        ...     event_type="scan",
        ...     message="Found 15 new giveaways",
        ...     details='{"count": 15, "page": 1}'
        ... )
        >>> log.is_info
        True
    """

    __tablename__ = "activity_logs"

    # ==================== Primary Key ====================
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Auto-increment primary key",
    )

    # ==================== Log Metadata ====================
    level: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
        comment="Log severity: info, warning, error",
    )
    event_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Event category: scan, entry, error, config",
    )

    # ==================== Log Content ====================
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Human-readable log message",
    )
    details: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Additional JSON-formatted details",
    )

    # ==================== Timestamp ====================
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
        comment="When log was created (UTC)",
    )
    # NOTE: No updated_at field - logs are immutable (insert-only)

    def __repr__(self) -> str:
        """String representation of ActivityLog."""
        return f"<ActivityLog(id={self.id}, level='{self.level}', type='{self.event_type}')>"

    @property
    def is_info(self) -> bool:
        """
        Check if log is info level.

        Returns:
            True if level is "info", False otherwise.
        """
        return self.level == "info"

    @property
    def is_warning(self) -> bool:
        """
        Check if log is warning level.

        Returns:
            True if level is "warning", False otherwise.
        """
        return self.level == "warning"

    @property
    def is_error(self) -> bool:
        """
        Check if log is error level.

        Returns:
            True if level is "error", False otherwise.
        """
        return self.level == "error"
