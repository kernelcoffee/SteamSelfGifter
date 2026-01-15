"""Giveaway repository with SteamGifts giveaway data queries.

This module provides a specialized repository for the Giveaway model with
methods for filtering eligible giveaways, tracking entries, and managing
giveaway visibility.
"""

from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models.giveaway import Giveaway
from models.game import Game
from repositories.base import BaseRepository


class GiveawayRepository(BaseRepository[Giveaway]):
    """
    Repository for Giveaway model with SteamGifts-specific queries.

    This repository extends BaseRepository to provide specialized methods
    for working with SteamGifts giveaway data, including eligibility filtering,
    entry tracking, and visibility management.

    Design Notes:
        - Giveaway code is unique and indexed for fast lookups
        - is_active is computed property (from end_time), not stored
        - game_name denormalized for performance (avoids JOIN)
        - Foreign key to Game is nullable (game may not be cached yet)

    Usage:
        >>> async with AsyncSessionLocal() as session:
        ...     repo = GiveawayRepository(session)
        ...     active = await repo.get_active()
        ...     giveaway = await repo.get_by_code("AbCd1")
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize GiveawayRepository with database session.

        Args:
            session: The async database session

        Example:
            >>> repo = GiveawayRepository(session)
        """
        super().__init__(Giveaway, session)

    async def get_all(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> List[Giveaway]:
        """
        Get all giveaways with proper ordering.

        Args:
            limit: Maximum number of giveaways to return (None = all)
            offset: Number of records to skip (for pagination)

        Returns:
            List of all giveaways, ordered by discovered_at (newest first)

        Example:
            >>> all_giveaways = await repo.get_all(limit=20, offset=0)
        """
        query = select(self.model).order_by(self.model.discovered_at.desc())

        if offset > 0:
            query = query.offset(offset)

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_code(self, code: str) -> Optional[Giveaway]:
        """
        Get giveaway by SteamGifts code.

        Args:
            code: Unique SteamGifts giveaway code (e.g., "AbCd1")

        Returns:
            Giveaway if found, None otherwise

        Example:
            >>> giveaway = await repo.get_by_code("AbCd1")
            >>> giveaway.game_name
            'Portal 2'
        """
        query = select(self.model).where(self.model.code == code)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_active(
        self, limit: Optional[int] = None, offset: int = 0, min_score: Optional[int] = None,
        is_safe: Optional[bool] = None
    ) -> List[Giveaway]:
        """
        Get all active (non-expired) giveaways.

        Note: Filters by end_time > now() to find active giveaways.
        is_active is a computed property, not stored in DB.

        Args:
            limit: Maximum number of giveaways to return (None = all)
            offset: Number of records to skip (for pagination)
            min_score: Minimum review score (0-10) to filter by
            is_safe: Filter by safety status (True=safe only, False=unsafe only, None=all)

        Returns:
            List of active giveaways, ordered by end_time (soonest first)

        Example:
            >>> active = await repo.get_active(limit=10, offset=20, min_score=7, is_safe=True)
            >>> len(active)
            10
        """
        now = datetime.utcnow()

        # Base conditions
        conditions = [
            self.model.end_time.isnot(None),
            self.model.end_time > now,
            self.model.is_hidden == False,  # noqa: E712
        ]

        # Add safety filter
        if is_safe is not None:
            conditions.append(self.model.is_safe == is_safe)  # noqa: E712

        # If min_score is specified, join with Game table and filter
        # Games default to review_score=0 when unknown
        if min_score is not None and min_score > 0:
            query = (
                select(self.model)
                .outerjoin(Game, self.model.game_id == Game.id)
                .where(
                    and_(
                        *conditions,
                        Game.review_score >= min_score,
                    )
                )
                .order_by(self.model.end_time)
            )
        else:
            query = (
                select(self.model)
                .where(and_(*conditions))
                .order_by(self.model.end_time)
            )

        if offset > 0:
            query = query.offset(offset)

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_eligible(
        self,
        min_price: int,
        min_score: Optional[int] = None,
        min_reviews: Optional[int] = None,
        max_price: Optional[int] = None,
        max_game_age: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Giveaway]:
        """
        Get eligible giveaways based on autojoin criteria.

        Filters active giveaways by:
        - Not hidden
        - Not already entered
        - Price within range
        - Optionally: minimum review score and count (requires game data)
        - Optionally: maximum game age in years

        Args:
            min_price: Minimum giveaway price in points
            min_score: Minimum game review score (0-10), optional
            min_reviews: Minimum number of reviews, optional
            max_price: Maximum giveaway price in points, optional
            max_game_age: Maximum game age in years, optional
            limit: Maximum number to return

        Returns:
            List of eligible giveaways, ordered by price (highest first)

        Example:
            >>> # Get high-value, well-reviewed giveaways not older than 5 years
            >>> eligible = await repo.get_eligible(
            ...     min_price=50,
            ...     min_score=8,
            ...     min_reviews=5000,
            ...     max_game_age=5,
            ...     limit=5
            ... )
        """
        now = datetime.utcnow()

        # Base filters: active, not hidden, not entered, price range
        conditions = [
            self.model.end_time.isnot(None),
            self.model.end_time > now,
            self.model.is_hidden == False,  # noqa: E712
            self.model.is_entered == False,  # noqa: E712
            self.model.price >= min_price,
        ]

        if max_price is not None:
            conditions.append(self.model.price <= max_price)

        # Determine if we need to JOIN with Game table
        needs_game_join = (
            min_score is not None or
            min_reviews is not None or
            max_game_age is not None
        )

        # If review/age filtering is requested, JOIN with Game table
        if needs_game_join:
            from models.game import Game

            query = (
                select(self.model)
                .join(Game, self.model.game_id == Game.id)
                .where(and_(*conditions))
            )

            # Add game review filters (games default to score=0 when unknown)
            if min_score is not None:
                query = query.where(Game.review_score >= min_score)

            if min_reviews is not None:
                query = query.where(Game.total_reviews >= min_reviews)

            # Add game age filter (release_date is stored as ISO format YYYY-MM-DD)
            if max_game_age is not None:
                min_release_year = now.year - max_game_age
                # Filter where release_date starts with a year >= min_release_year
                # release_date is stored as "YYYY-MM-DD" ISO format
                min_release_date = f"{min_release_year}-01-01"
                query = query.where(Game.release_date >= min_release_date)

            query = query.order_by(self.model.price.desc())
        else:
            query = (
                select(self.model)
                .where(and_(*conditions))
                .order_by(self.model.price.desc())
            )

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        giveaways = list(result.scalars().all())

        return giveaways

    async def get_by_game(self, game_id: int) -> List[Giveaway]:
        """
        Get all giveaways for a specific game.

        Args:
            game_id: Steam App ID

        Returns:
            List of giveaways for this game

        Example:
            >>> giveaways = await repo.get_by_game(730)  # CS:GO
        """
        query = select(self.model).where(self.model.game_id == game_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_hidden(self) -> List[Giveaway]:
        """
        Get all hidden giveaways.

        Returns:
            List of giveaways marked as hidden by user

        Example:
            >>> hidden = await repo.get_hidden()
        """
        query = select(self.model).where(self.model.is_hidden == True)  # noqa: E712
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_entered(
        self, limit: Optional[int] = None, active_only: bool = False
    ) -> List[Giveaway]:
        """
        Get entered giveaways.

        Args:
            limit: Maximum number to return
            active_only: If True, only return non-expired giveaways

        Returns:
            List of giveaways we've entered, ordered by entered_at (most recent first)

        Example:
            >>> entered = await repo.get_entered(limit=20, active_only=True)
        """
        now = datetime.utcnow()

        conditions = [self.model.is_entered == True]  # noqa: E712

        if active_only:
            # Only include giveaways that haven't expired
            conditions.append(self.model.end_time.isnot(None))
            conditions.append(self.model.end_time > now)

        query = (
            select(self.model)
            .where(and_(*conditions))
            .order_by(self.model.entered_at.desc())
        )

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_wishlist(
        self, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> List[Giveaway]:
        """
        Get active wishlist giveaways.

        Args:
            limit: Maximum number to return
            offset: Number of records to skip

        Returns:
            List of wishlist giveaways that are still active (not expired)

        Example:
            >>> wishlist = await repo.get_wishlist(limit=20)
        """
        now = datetime.utcnow()
        query = (
            select(self.model)
            .where(
                self.model.is_wishlist == True,  # noqa: E712
                self.model.is_hidden == False,  # noqa: E712
                (self.model.end_time == None) | (self.model.end_time > now),  # noqa: E711
            )
            .order_by(self.model.end_time.asc())
        )

        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_won(
        self, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> List[Giveaway]:
        """
        Get won giveaways.

        Args:
            limit: Maximum number to return
            offset: Number of records to skip

        Returns:
            List of won giveaways, ordered by won_at (most recent first)

        Example:
            >>> wins = await repo.get_won(limit=20)
        """
        query = (
            select(self.model)
            .where(self.model.is_won == True)  # noqa: E712
            .order_by(self.model.won_at.desc())
        )

        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_won(self) -> int:
        """
        Count total number of won giveaways.

        Returns:
            Total number of wins

        Example:
            >>> count = await repo.count_won()
            >>> print(f"Total wins: {count}")
        """
        from sqlalchemy import func

        query = select(func.count()).select_from(self.model).where(
            self.model.is_won == True  # noqa: E712
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def hide_giveaway(self, giveaway_id: int) -> Optional[Giveaway]:
        """
        Mark giveaway as hidden.

        Args:
            giveaway_id: Giveaway ID to hide

        Returns:
            Updated giveaway, or None if not found

        Example:
            >>> giveaway = await repo.hide_giveaway(123)
            >>> giveaway.is_hidden
            True
        """
        return await self.update(giveaway_id, is_hidden=True)

    async def unhide_giveaway(self, giveaway_id: int) -> Optional[Giveaway]:
        """
        Mark giveaway as not hidden.

        Args:
            giveaway_id: Giveaway ID to unhide

        Returns:
            Updated giveaway, or None if not found

        Example:
            >>> giveaway = await repo.unhide_giveaway(123)
            >>> giveaway.is_hidden
            False
        """
        return await self.update(giveaway_id, is_hidden=False)

    async def mark_entered(
        self, giveaway_id: int, entered_at: Optional[datetime] = None
    ) -> Optional[Giveaway]:
        """
        Mark giveaway as entered.

        Args:
            giveaway_id: Giveaway ID
            entered_at: When entered (defaults to now)

        Returns:
            Updated giveaway, or None if not found

        Example:
            >>> giveaway = await repo.mark_entered(123)
            >>> giveaway.is_entered
            True
        """
        if entered_at is None:
            entered_at = datetime.utcnow()

        return await self.update(
            giveaway_id, is_entered=True, entered_at=entered_at
        )

    async def get_expiring_soon(
        self, hours: int = 24, limit: Optional[int] = None
    ) -> List[Giveaway]:
        """
        Get giveaways expiring within specified hours.

        Args:
            hours: Number of hours (default: 24)
            limit: Maximum number to return

        Returns:
            List of giveaways expiring soon, ordered by end_time (soonest first)

        Example:
            >>> # Get giveaways ending in next 6 hours
            >>> expiring = await repo.get_expiring_soon(hours=6, limit=10)
        """
        now = datetime.utcnow()
        cutoff = now + timedelta(hours=hours)

        query = (
            select(self.model)
            .where(
                and_(
                    self.model.end_time.isnot(None),
                    self.model.end_time > now,
                    self.model.end_time <= cutoff,
                    self.model.is_hidden == False,  # noqa: E712
                    self.model.is_entered == False,  # noqa: E712
                )
            )
            .order_by(self.model.end_time)
        )

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_active(self) -> int:
        """
        Count active (non-expired) giveaways.

        Returns:
            Number of active giveaways

        Example:
            >>> count = await repo.count_active()
            >>> print(f"Active giveaways: {count}")
        """
        now = datetime.utcnow()
        query = select(self.model).where(
            and_(
                self.model.end_time.isnot(None),
                self.model.end_time > now,
            )
        )
        result = await self.session.execute(query)
        return len(list(result.scalars().all()))

    async def count_entered(self) -> int:
        """
        Count giveaways we've entered.

        Returns:
            Number of entered giveaways

        Example:
            >>> count = await repo.count_entered()
        """
        query = select(self.model).where(self.model.is_entered == True)  # noqa: E712
        result = await self.session.execute(query)
        return len(list(result.scalars().all()))

    async def search_by_game_name(
        self, query_text: str, limit: Optional[int] = None
    ) -> List[Giveaway]:
        """
        Search giveaways by game name (case-insensitive).

        Args:
            query_text: Search query
            limit: Maximum number to return

        Returns:
            List of matching giveaways

        Example:
            >>> results = await repo.search_by_game_name("portal", limit=10)
        """
        query = (
            select(self.model)
            .where(self.model.game_name.ilike(f"%{query_text}%"))
            .order_by(self.model.created_at.desc())
        )

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_safe_giveaways(
        self, min_safety_score: int = 80, limit: Optional[int] = None
    ) -> List[Giveaway]:
        """
        Get giveaways marked as safe with high safety scores.

        Args:
            min_safety_score: Minimum safety score (0-100)
            limit: Maximum number to return

        Returns:
            List of safe giveaways

        Example:
            >>> safe = await repo.get_safe_giveaways(min_safety_score=90)
        """
        query = (
            select(self.model)
            .where(
                and_(
                    self.model.is_safe == True,  # noqa: E712
                    self.model.safety_score >= min_safety_score,
                )
            )
            .order_by(self.model.safety_score.desc())
        )

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_unsafe_giveaways(self) -> List[Giveaway]:
        """
        Get giveaways marked as unsafe (potential scams).

        Returns:
            List of unsafe giveaways

        Example:
            >>> unsafe = await repo.get_unsafe_giveaways()
        """
        query = select(self.model).where(self.model.is_safe == False)  # noqa: E712
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_next_expiring_entered(self) -> Optional[Giveaway]:
        """
        Get the next entered giveaway that will expire.

        Used for scheduling win checks when giveaways end.

        Returns:
            The entered giveaway with the soonest end_time, or None if no
            entered giveaways are pending.

        Example:
            >>> next_ga = await repo.get_next_expiring_entered()
            >>> if next_ga:
            ...     print(f"Next expires at: {next_ga.end_time}")
        """
        now = datetime.utcnow()
        query = (
            select(self.model)
            .where(
                and_(
                    self.model.is_entered == True,  # noqa: E712
                    self.model.is_won == False,  # noqa: E712
                    self.model.end_time.isnot(None),
                    self.model.end_time > now,
                )
            )
            .order_by(self.model.end_time.asc())
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def count_entered_since(self, since: datetime) -> int:
        """
        Count giveaways entered since a specific date.

        Args:
            since: Start date to count from

        Returns:
            Number of giveaways entered since the date

        Example:
            >>> from datetime import datetime, timedelta
            >>> thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            >>> count = await repo.count_entered_since(thirty_days_ago)
        """
        from sqlalchemy import func

        query = select(func.count()).select_from(self.model).where(
            and_(
                self.model.is_entered == True,  # noqa: E712
                self.model.entered_at.isnot(None),
                self.model.entered_at >= since,
            )
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def count_won_since(self, since: datetime) -> int:
        """
        Count giveaways won since a specific date.

        Args:
            since: Start date to count from

        Returns:
            Number of giveaways won since the date

        Example:
            >>> from datetime import datetime, timedelta
            >>> thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            >>> count = await repo.count_won_since(thirty_days_ago)
        """
        from sqlalchemy import func

        query = select(func.count()).select_from(self.model).where(
            and_(
                self.model.is_won == True,  # noqa: E712
                self.model.won_at.isnot(None),
                self.model.won_at >= since,
            )
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_stats_since(self, since: datetime) -> dict:
        """
        Get giveaway statistics since a specific date.

        Args:
            since: Start date to count from

        Returns:
            Dict with giveaway stats (total, active, entered, hidden, wins, win_rate)

        Example:
            >>> from datetime import datetime, timedelta
            >>> week_ago = datetime.utcnow() - timedelta(days=7)
            >>> stats = await repo.get_stats_since(week_ago)
        """
        from sqlalchemy import func, case

        now = datetime.utcnow()

        query = select(
            func.count().label("total"),
            func.sum(
                case(
                    (
                        and_(
                            self.model.end_time.isnot(None),
                            self.model.end_time > now,
                            self.model.is_hidden == False,  # noqa: E712
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("active"),
            func.sum(
                case((self.model.is_entered == True, 1), else_=0)  # noqa: E712
            ).label("entered"),
            func.sum(
                case((self.model.is_hidden == True, 1), else_=0)  # noqa: E712
            ).label("hidden"),
            func.sum(
                case((self.model.is_won == True, 1), else_=0)  # noqa: E712
            ).label("wins"),
        ).where(self.model.discovered_at >= since)

        result = await self.session.execute(query)
        row = result.one()

        entered = row.entered or 0
        wins = row.wins or 0
        win_rate = (wins / entered * 100) if entered > 0 else 0.0

        return {
            "total": row.total or 0,
            "active": row.active or 0,
            "entered": entered,
            "hidden": row.hidden or 0,
            "wins": wins,
            "win_rate": win_rate,
        }

    async def create_or_update_by_code(
        self, code: str, **kwargs
    ) -> Giveaway:
        """
        Create new giveaway or update existing by code (upsert).

        Args:
            code: Unique SteamGifts code
            **kwargs: Giveaway fields to set

        Returns:
            Created or updated giveaway

        Example:
            >>> giveaway = await repo.create_or_update_by_code(
            ...     code="AbCd1",
            ...     game_name="Portal 2",
            ...     price=50
            ... )
        """
        existing = await self.get_by_code(code)

        if existing:
            # Update existing
            for key, value in kwargs.items():
                setattr(existing, key, value)
            return existing
        else:
            # Create new
            kwargs["code"] = code
            return await self.create(**kwargs)

    async def get_safety_stats(self) -> dict:
        """
        Get safety statistics for giveaways.

        Returns:
            Dict with safety stats (checked, safe, unsafe, unchecked)

        Example:
            >>> stats = await repo.get_safety_stats()
            >>> print(f"Safe: {stats['safe']}, Unsafe: {stats['unsafe']}")
        """
        from sqlalchemy import func, case

        query = select(
            func.count().label("total"),
            func.sum(
                case((self.model.is_safe.isnot(None), 1), else_=0)
            ).label("checked"),
            func.sum(
                case((self.model.is_safe == True, 1), else_=0)  # noqa: E712
            ).label("safe"),
            func.sum(
                case((self.model.is_safe == False, 1), else_=0)  # noqa: E712
            ).label("unsafe"),
        )

        result = await self.session.execute(query)
        row = result.one()

        total = row.total or 0
        checked = row.checked or 0

        return {
            "total": total,
            "checked": checked,
            "unchecked": total - checked,
            "safe": row.safe or 0,
            "unsafe": row.unsafe or 0,
        }

    async def get_unchecked_eligible(self, limit: int = 1) -> List[Giveaway]:
        """
        Get eligible giveaways that haven't been safety checked yet.

        These are active, non-entered, non-hidden giveaways where is_safe is NULL.
        Used by the background safety check job to process giveaways slowly.

        Args:
            limit: Maximum number to return (default: 1 for slow processing)

        Returns:
            List of giveaways needing safety check

        Example:
            >>> unchecked = await repo.get_unchecked_eligible(limit=1)
            >>> if unchecked:
            ...     await safety_check(unchecked[0])
        """
        now = datetime.utcnow()

        query = (
            select(self.model)
            .where(
                and_(
                    self.model.end_time.isnot(None),
                    self.model.end_time > now,
                    self.model.is_hidden == False,  # noqa: E712
                    self.model.is_entered == False,  # noqa: E712
                    self.model.is_safe.is_(None),  # Not yet checked
                )
            )
            .order_by(self.model.end_time.asc())  # Prioritize soon-expiring
            .limit(limit)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())
