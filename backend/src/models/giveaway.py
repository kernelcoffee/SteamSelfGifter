"""SteamGifts giveaway data model."""

from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class Giveaway(Base, TimestampMixin):
    """
    SteamGifts giveaway information discovered during scanning.

    This model stores giveaways found on SteamGifts.com, tracking their
    status, game information, and entry details for automated processing.

    Attributes:
        id: Auto-increment primary key
        code: Unique SteamGifts giveaway code (from URL)
        url: Full URL to the giveaway page

        Game Information:
            game_id: Foreign key to Game model (Steam App ID)
            game_name: Denormalized game name for quick display

        Giveaway Details:
            price: Entry cost in SteamGifts points
            copies: Number of copies being given away
            end_time: When giveaway ends (UTC)
            is_active: Computed property - true if not expired

        Status Flags:
            is_hidden: User manually hid this giveaway
            is_entered: Whether we've entered this giveaway

        Safety Analysis:
            is_safe: Scam detection result (True/False/None)
            safety_score: Confidence score for scam detection (0-100)

        Timestamps:
            discovered_at: When we first found this giveaway
            entered_at: When we entered this giveaway
            created_at: DB record creation (from TimestampMixin)
            updated_at: Last DB update (from TimestampMixin)

    Design Notes:
        - code is unique and indexed for fast lookups
        - is_active computed at runtime from end_time (not stored)
        - game_name denormalized to avoid JOIN for display
        - Foreign key to Game is nullable (game may not be cached yet)

    Example:
        >>> giveaway = Giveaway(
        ...     code="AbCd1",
        ...     url="https://www.steamgifts.com/giveaway/AbCd1/game-name",
        ...     game_name="Portal 2",
        ...     price=50,
        ...     end_time=datetime(2025, 12, 31, 23, 59)
        ... )
        >>> giveaway.is_active
        True
        >>> giveaway.time_remaining
        31536000  # seconds
    """

    __tablename__ = "giveaways"

    # ==================== Primary Key ====================
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Auto-increment primary key",
    )

    # ==================== Unique Identifiers ====================
    code: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
        index=True,
        comment="Unique SteamGifts giveaway code",
    )
    url: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Full giveaway URL",
    )

    # ==================== Game Reference ====================
    game_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("games.id"),
        nullable=True,
        comment="Steam App ID (foreign key to games)",
    )
    game_name: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Game name (denormalized for display)",
    )

    # ==================== Giveaway Details ====================
    price: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Entry cost in points",
    )
    copies: Mapped[int] = mapped_column(
        Integer,
        default=1,
        comment="Number of copies available",
    )
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="When giveaway ends (UTC)",
    )
    # NOTE: is_active computed from end_time, not stored

    # ==================== Status Flags ====================
    is_hidden: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="User manually hid this giveaway",
    )
    is_entered: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Whether we entered this giveaway",
    )
    is_wishlist: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Game is on user's Steam wishlist",
    )
    is_won: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Whether user won this giveaway",
    )
    won_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="When the win was detected",
    )

    # ==================== Safety Analysis ====================
    is_safe: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="Scam detection result",
    )
    safety_score: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Scam detection confidence (0-100)",
    )

    # ==================== Timestamps ====================
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="When we first discovered this",
    )
    entered_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="When we entered this giveaway",
    )

    def __repr__(self) -> str:
        """String representation of Giveaway."""
        return f"<Giveaway(code='{self.code}', game='{self.game_name}', price={self.price})>"

    @property
    def is_active(self) -> bool:
        """
        Check if giveaway is still active.

        Returns:
            True if current time < end_time, False if expired.
            Returns True if end_time is unknown (assume active).

        Note:
            This is a computed property, not stored in the database.
        """
        if not self.end_time:
            return True  # Unknown end time, assume active
        return datetime.utcnow() < self.end_time

    @property
    def is_expired(self) -> bool:
        """
        Check if giveaway has expired.

        Returns:
            Inverse of is_active.
        """
        return not self.is_active

    @property
    def time_remaining(self) -> int | None:
        """
        Get seconds remaining until giveaway ends.

        Returns:
            Seconds remaining (int), 0 if expired, or None if end_time unknown.

        Example:
            >>> giveaway.end_time = datetime.utcnow() + timedelta(hours=2)
            >>> giveaway.time_remaining
            7200  # 2 hours in seconds
        """
        if not self.end_time:
            return None
        if self.is_expired:
            return 0
        return int((self.end_time - datetime.utcnow()).total_seconds())
