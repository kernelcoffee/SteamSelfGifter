"""Application settings model for SteamSelfGifter."""

from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class Settings(Base, TimestampMixin):
    """
    Application settings stored in database (singleton pattern with id=1).

    This model stores all user-configurable settings for the application.
    Only one instance should exist in the database (singleton pattern).

    Attributes:
        id: Primary key, always 1 (singleton)

        SteamGifts Authentication:
            phpsessid: SteamGifts session cookie for authentication
            user_agent: Browser user agent string for HTTP requests
            xsrf_token: Anti-CSRF token from SteamGifts (extracted from pages)

        DLC Settings:
            dlc_enabled: Whether to enter DLC giveaways (default: False)

        Auto-join Settings:
            autojoin_enabled: Enable automatic giveaway entry (default: False)
            autojoin_start_at: Start entering when points >= this value (default: 350)
            autojoin_stop_at: Stop entering when points <= this value (default: 200)
            autojoin_min_price: Minimum giveaway price in points to enter (default: 10)
            autojoin_min_score: Minimum Steam review score (0-10) required (default: 7)
            autojoin_min_reviews: Minimum number of reviews required (default: 1000)

        Scheduler Settings:
            scan_interval_minutes: How often to scan for giveaways (default: 30 min)
            max_entries_per_cycle: Max entries per scan cycle (None = unlimited)
            automation_enabled: Master switch for automation (default: False)

        Advanced Settings:
            max_scan_pages: Maximum SteamGifts pages to scan per cycle (default: 3)
            entry_delay_min: Minimum delay between entries in seconds (default: 8)
            entry_delay_max: Maximum delay between entries in seconds (default: 12)

        Metadata:
            last_synced_at: Last time settings were synced with SteamGifts
            created_at: When settings were first created (from TimestampMixin)
            updated_at: Last time settings were modified (from TimestampMixin)

    Design Notes:
        - current_points is NOT stored in DB (fetched dynamically from SteamGifts)
        - This prevents stale point balance data
        - Singleton pattern ensures only one settings record exists

    Example:
        >>> settings = Settings(
        ...     id=1,
        ...     phpsessid="abc123",
        ...     autojoin_enabled=True,
        ...     autojoin_start_at=400
        ... )
        >>> session.add(settings)
        >>> await session.commit()
    """

    __tablename__ = "settings"

    # Primary key (always 1 for singleton)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # ==================== SteamGifts Authentication ====================
    phpsessid: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        comment="SteamGifts session cookie for authentication",
    )
    user_agent: Mapped[str] = mapped_column(
        String,
        default="Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:82.0) Gecko/20100101 Firefox/82.0",
        comment="Browser user agent for HTTP requests",
    )
    xsrf_token: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        comment="Anti-CSRF token from SteamGifts",
    )
    # NOTE: current_points is fetched dynamically from SteamGifts, not stored here

    # ==================== DLC Settings ====================
    dlc_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Whether to enter DLC giveaways",
    )

    # ==================== Safety Settings ====================
    safety_check_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="Check giveaways for traps before auto-entering",
    )
    auto_hide_unsafe: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="Automatically hide unsafe giveaways on SteamGifts",
    )

    # ==================== Auto-join Settings ====================
    autojoin_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Enable automatic giveaway entry",
    )
    autojoin_start_at: Mapped[int] = mapped_column(
        Integer,
        default=350,
        comment="Start entering when points >= this value",
    )
    autojoin_stop_at: Mapped[int] = mapped_column(
        Integer,
        default=200,
        comment="Stop entering when points <= this value",
    )
    autojoin_min_price: Mapped[int] = mapped_column(
        Integer,
        default=10,
        comment="Minimum giveaway price in points",
    )
    autojoin_min_score: Mapped[int] = mapped_column(
        Integer,
        default=7,
        comment="Minimum Steam review score (0-10)",
    )
    autojoin_min_reviews: Mapped[int] = mapped_column(
        Integer,
        default=1000,
        comment="Minimum number of reviews required",
    )
    autojoin_max_game_age: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
        comment="Maximum game age in years (None = no limit)",
    )

    # ==================== Scheduler Settings ====================
    scan_interval_minutes: Mapped[int] = mapped_column(
        Integer,
        default=30,
        comment="Scan interval in minutes",
    )
    max_entries_per_cycle: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Maximum entries per cycle (None = unlimited)",
    )
    automation_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Master switch for automation",
    )

    # ==================== Advanced Settings ====================
    max_scan_pages: Mapped[int] = mapped_column(
        Integer,
        default=3,
        comment="Maximum SteamGifts pages to scan",
    )
    entry_delay_min: Mapped[int] = mapped_column(
        Integer,
        default=8,
        comment="Minimum delay between entries (seconds)",
    )
    entry_delay_max: Mapped[int] = mapped_column(
        Integer,
        default=12,
        comment="Maximum delay between entries (seconds)",
    )

    # ==================== Metadata ====================
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="Last sync with SteamGifts",
    )

    def __repr__(self) -> str:
        """String representation of Settings."""
        return f"<Settings(id={self.id}, autojoin={self.autojoin_enabled})>"
