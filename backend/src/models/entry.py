"""Giveaway entry tracking model."""

from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class Entry(Base, TimestampMixin):
    """
    Giveaway entry tracking for analytics and history.

    This model records all entry attempts (successful or failed) to provide
    analytics, debugging information, and entry history.

    Attributes:
        id: Auto-increment primary key
        giveaway_id: Foreign key to Giveaway model (indexed)

        Entry Details:
            points_spent: SteamGifts points spent on entry
            entry_type: How entry was made - "manual", "auto", "wishlist"
            status: Entry result - "success", "failed", "pending"

        Tracking:
            entered_at: When entry attempt was made (UTC)
            error_message: Error details if entry failed
            created_at: DB record creation (from TimestampMixin)
            updated_at: Last DB update (from TimestampMixin)

        Computed Properties:
            is_successful: True if status == "success"
            is_failed: True if status == "failed"
            is_pending: True if status == "pending"

    Entry Types:
        - "manual": User manually entered via UI/API
        - "auto": Automatically entered via autojoin scheduler
        - "wishlist": Automatically entered from wishlist scan

    Status Values:
        - "success": Entry completed successfully
        - "failed": Entry attempt failed (see error_message)
        - "pending": Entry in progress (rare, async operations)

    Design Notes:
        - Stores ALL entry attempts including failures for analytics
        - Foreign key ensures referential integrity with Giveaway
        - Indexed on giveaway_id for fast lookups
        - error_message helps debug automation issues

    Example:
        >>> entry = Entry(
        ...     giveaway_id=123,
        ...     points_spent=50,
        ...     entry_type="auto",
        ...     status="success"
        ... )
        >>> entry.is_successful
        True
    """

    __tablename__ = "entries"

    # ==================== Primary Key ====================
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Auto-increment primary key",
    )

    # ==================== Giveaway Reference ====================
    giveaway_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("giveaways.id"),
        nullable=False,
        index=True,
        comment="Foreign key to giveaway",
    )

    # ==================== Entry Details ====================
    points_spent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Points spent on entry",
    )
    entry_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Entry method: manual, auto, wishlist",
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Entry status: success, failed, pending",
    )

    # ==================== Tracking ====================
    entered_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="When entry was attempted (UTC)",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error details if entry failed",
    )

    def __repr__(self) -> str:
        """String representation of Entry."""
        return (
            f"<Entry(id={self.id}, giveaway_id={self.giveaway_id}, "
            f"status='{self.status}', points={self.points_spent})>"
        )

    @property
    def is_successful(self) -> bool:
        """
        Check if entry was successful.

        Returns:
            True if status is "success", False otherwise.
        """
        return self.status == "success"

    @property
    def is_failed(self) -> bool:
        """
        Check if entry failed.

        Returns:
            True if status is "failed", False otherwise.
        """
        return self.status == "failed"

    @property
    def is_pending(self) -> bool:
        """
        Check if entry is still pending.

        Returns:
            True if status is "pending", False otherwise.
        """
        return self.status == "pending"
