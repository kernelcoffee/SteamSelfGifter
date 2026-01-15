"""Game repository with Steam game data queries.

This module provides a specialized repository for the Game model with
methods for searching games, finding stale cache entries, and managing
Steam game metadata.
"""

from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models.game import Game
from repositories.base import BaseRepository


class GameRepository(BaseRepository[Game]):
    """
    Repository for Game model with Steam-specific queries.

    This repository extends BaseRepository to provide specialized methods
    for working with Steam game data, including cache management and search.

    Design Notes:
        - Game uses Steam App ID as primary key (not auto-increment)
        - Caching reduces Steam API calls
        - needs_refresh is computed property, not stored
        - Review data used for autojoin filtering

    Usage:
        >>> async with AsyncSessionLocal() as session:
        ...     repo = GameRepository(session)
        ...     game = await repo.get_by_app_id(730)
        ...     stale = await repo.get_stale_games()
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize GameRepository with database session.

        Args:
            session: The async database session

        Example:
            >>> repo = GameRepository(session)
        """
        super().__init__(Game, session)

    async def get_by_app_id(self, app_id: int) -> Optional[Game]:
        """
        Get game by Steam App ID.

        Convenience method that wraps get_by_id with a more descriptive name
        for the Game model where the primary key is the Steam App ID.

        Args:
            app_id: Steam App ID

        Returns:
            The Game instance if found, None otherwise

        Example:
            >>> game = await repo.get_by_app_id(730)  # Counter-Strike 2
            >>> if game:
            ...     print(game.name)
        """
        return await self.get_by_id(app_id)

    async def search_by_name(
        self, query: str, limit: int = 10
    ) -> List[Game]:
        """
        Search games by name (case-insensitive partial match).

        Args:
            query: Search query string
            limit: Maximum number of results to return (default: 10)

        Returns:
            List of matching Game instances

        Example:
            >>> games = await repo.search_by_name("counter-strike")
            >>> for game in games:
            ...     print(f"{game.id}: {game.name}")
        """
        stmt = (
            select(Game)
            .where(Game.name.ilike(f"%{query}%"))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_stale_games(
        self, days_threshold: int = 7, limit: Optional[int] = None
    ) -> List[Game]:
        """
        Get games with stale cached data that need refreshing.

        Returns games where:
        - last_refreshed_at is None (never refreshed), OR
        - last_refreshed_at is older than days_threshold

        Args:
            days_threshold: Number of days before data is considered stale (default: 7)
            limit: Maximum number of results to return (None for all)

        Returns:
            List of Game instances that need refreshing

        Example:
            >>> stale = await repo.get_stale_games(days_threshold=7, limit=50)
            >>> for game in stale:
            ...     # Refresh game data from Steam API
            ...     pass
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_threshold)

        stmt = select(Game).where(
            or_(
                Game.last_refreshed_at.is_(None),
                Game.last_refreshed_at < cutoff_date,
            )
        )

        if limit:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_type(self, game_type: str) -> List[Game]:
        """
        Get all games of a specific type.

        Args:
            game_type: Type to filter by ("game", "dlc", or "bundle")

        Returns:
            List of Game instances matching the type

        Example:
            >>> dlcs = await repo.get_by_type("dlc")
            >>> games = await repo.get_by_type("game")
        """
        return await self.filter_by(type=game_type)

    async def get_bundles(self) -> List[Game]:
        """
        Get all bundle entries.

        Convenience method to retrieve games marked as bundles.

        Returns:
            List of Game instances where is_bundle=True

        Example:
            >>> bundles = await repo.get_bundles()
            >>> for bundle in bundles:
            ...     print(f"{bundle.name}: {len(bundle.bundle_content)} items")
        """
        return await self.filter_by(is_bundle=True)

    async def get_by_main_game(self, game_id: int) -> List[Game]:
        """
        Get all DLCs/content for a specific game.

        Args:
            game_id: The main game's Steam App ID

        Returns:
            List of Game instances (DLCs/bundles) linked to the main game

        Example:
            >>> dlcs = await repo.get_by_main_game(730)  # Get all CS2 DLCs
            >>> for dlc in dlcs:
            ...     print(f"DLC: {dlc.name}")
        """
        return await self.filter_by(game_id=game_id)

    async def get_highly_rated(
        self, min_score: int = 7, min_reviews: int = 1000, limit: int = 50
    ) -> List[Game]:
        """
        Get highly rated games matching minimum thresholds.

        Args:
            min_score: Minimum review score (0-10 scale, default: 7)
            min_reviews: Minimum number of reviews (default: 1000)
            limit: Maximum number of results (default: 50)

        Returns:
            List of highly rated Game instances

        Example:
            >>> top_games = await repo.get_highly_rated(min_score=8, min_reviews=5000)
            >>> for game in top_games:
            ...     print(f"{game.name}: {game.review_score}/10")
        """
        stmt = (
            select(Game)
            .where(
                Game.review_score >= min_score,
                Game.total_reviews >= min_reviews,
            )
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_refreshed(self, app_id: int) -> Optional[Game]:
        """
        Mark a game as refreshed by updating last_refreshed_at to now.

        Args:
            app_id: Steam App ID of the game to mark

        Returns:
            The updated Game instance, or None if not found

        Example:
            >>> game = await repo.mark_refreshed(730)
            >>> await session.commit()

        Note:
            This method does NOT commit the transaction. The caller must
            call session.commit() to persist changes to the database.
        """
        return await self.update(app_id, last_refreshed_at=datetime.utcnow())

    async def bulk_mark_refreshed(self, app_ids: List[int]) -> None:
        """
        Mark multiple games as refreshed.

        Args:
            app_ids: List of Steam App IDs to mark as refreshed

        Example:
            >>> await repo.bulk_mark_refreshed([730, 570, 440])
            >>> await session.commit()

        Note:
            This method does NOT commit the transaction. The caller must
            call session.commit() to persist changes to the database.
        """
        now = datetime.utcnow()
        for app_id in app_ids:
            await self.update(app_id, last_refreshed_at=now)

    async def create_or_update(self, app_id: int, **kwargs) -> Game:
        """
        Create a new game or update existing one.

        This is an upsert operation that checks if the game exists and
        either creates or updates it accordingly.

        Args:
            app_id: Steam App ID
            **kwargs: Field values to set

        Returns:
            The Game instance (created or updated)

        Example:
            >>> game = await repo.create_or_update(
            ...     730,
            ...     name="Counter-Strike 2",
            ...     type="game",
            ...     review_score=9
            ... )
            >>> await session.commit()

        Note:
            This method does NOT commit the transaction. The caller must
            call session.commit() to persist changes to the database.
        """
        existing = await self.get_by_app_id(app_id)

        if existing:
            # Update existing game
            for key, value in kwargs.items():
                setattr(existing, key, value)
            await self.session.flush()
            return existing
        else:
            # Create new game
            return await self.create(id=app_id, **kwargs)

    async def count_by_type(self) -> dict:
        """
        Get count of games by type.

        Returns:
            Dictionary with counts for each type (game, dlc, bundle)

        Example:
            >>> counts = await repo.count_by_type()
            >>> print(f"Games: {counts['game']}, DLCs: {counts['dlc']}")
        """
        games = await self.filter_by(type="game")
        dlcs = await self.filter_by(type="dlc")
        bundles = await self.filter_by(type="bundle")

        return {
            "game": len(games),
            "dlc": len(dlcs),
            "bundle": len(bundles),
        }

    async def get_without_reviews(self, limit: Optional[int] = None) -> List[Game]:
        """
        Get games that don't have review data yet.

        Args:
            limit: Maximum number of results (None for all)

        Returns:
            List of Game instances without review data

        Example:
            >>> games = await repo.get_without_reviews(limit=100)
            >>> # Fetch review data for these games
        """
        stmt = select(Game).where(
            or_(
                Game.total_reviews.is_(None),
                Game.total_reviews == 0,
            )
        )

        if limit:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
