"""Steam game/DLC/bundle data model."""

from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class Game(Base, TimestampMixin):
    """
    Steam game, DLC, or bundle information cached from Steam API.

    This model stores game metadata fetched from the Steam API to avoid
    repeated API calls and provide quick lookups during giveaway filtering.

    Attributes:
        id: Steam App ID (primary key, not auto-increment)
        name: Game/DLC/bundle name
        type: Content type - "game", "dlc", or "bundle"
        release_date: Release date string from Steam

        Review Data:
            review_score: Overall review score (0-10 scale)
            total_positive: Number of positive reviews
            total_negative: Number of negative reviews
            total_reviews: Total number of reviews

        Bundle Information:
            is_bundle: Whether this is a bundle (default: False)
            bundle_content: List of Steam App IDs in bundle (JSON array)
            game_id: Main game App ID (for DLC or bundles)

        Cache Management:
            last_refreshed_at: When data was last fetched from Steam API
            needs_refresh: Computed property - true if data older than 7 days

        Additional Metadata:
            description: Game description text
            price: Current price in cents (USD)
            created_at: First time cached (from TimestampMixin)
            updated_at: Last update time (from TimestampMixin)

    Design Notes:
        - Primary key is Steam App ID (externally defined, not auto-increment)
        - needs_refresh is computed at runtime (not stored in DB)
        - Caching reduces Steam API calls and improves response time
        - Review data used for autojoin filtering

    Example:
        >>> game = Game(
        ...     id=730,  # CS:GO
        ...     name="Counter-Strike: Global Offensive",
        ...     type="game",
        ...     review_score=9,
        ...     total_positive=3500000,
        ...     total_negative=400000
        ... )
        >>> print(game.review_percentage)
        89.74...
    """

    __tablename__ = "games"

    # ==================== Primary Key ====================
    # Steam App ID (externally defined, not auto-increment)
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="Steam App ID",
    )

    # ==================== Basic Information ====================
    name: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Game/DLC/bundle name",
    )
    type: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Content type: game, dlc, or bundle",
    )
    release_date: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        comment="Release date from Steam",
    )

    # ==================== Review Data ====================
    review_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Overall review score (0-10), 0 means no reviews or unknown",
    )
    total_positive: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of positive reviews",
    )
    total_negative: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of negative reviews",
    )
    total_reviews: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total number of reviews",
    )

    # ==================== Bundle Information ====================
    is_bundle: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Whether this is a bundle",
    )
    bundle_content: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="List of Steam App IDs in bundle",
    )
    game_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Main game App ID (for DLC/bundles)",
    )

    # ==================== Cache Management ====================
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="Last Steam API fetch time",
    )
    # NOTE: needs_refresh computed at runtime, not stored in DB

    # ==================== Additional Metadata ====================
    header_image: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="Steam header image URL",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Game description",
    )
    price: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Current price in cents (USD)",
    )

    def __repr__(self) -> str:
        """String representation of Game."""
        return f"<Game(id={self.id}, name='{self.name}', type='{self.type}')>"

    @property
    def review_percentage(self) -> float | None:
        """
        Calculate positive review percentage.

        Returns:
            Percentage of positive reviews (0-100), or None if no reviews.

        Example:
            >>> game.total_positive = 900
            >>> game.total_reviews = 1000
            >>> game.review_percentage
            90.0
        """
        if self.total_reviews and self.total_reviews > 0:
            return (self.total_positive / self.total_reviews) * 100
        return None

    @property
    def needs_refresh(self) -> bool:
        """
        Check if cached data needs refreshing.

        Data is considered stale if:
        - Never refreshed (last_refreshed_at is None)
        - Older than 7 days

        Returns:
            True if data needs refresh, False otherwise.

        Note:
            This is a computed property, not stored in the database.
        """
        if not self.last_refreshed_at:
            return True
        days_old = (datetime.utcnow() - self.last_refreshed_at).days
        return days_old > 7
