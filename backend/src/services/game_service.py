"""Game service with business logic for game data management.

This module provides the service layer for game operations, coordinating
between the GameRepository and external Steam API client.
"""

from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.game import GameRepository
from utils.steam_client import SteamClient, SteamAPIError
from models.game import Game


class GameService:
    """
    Service for game data management.

    This service coordinates between GameRepository and SteamClient to:
    - Fetch game data from Steam API
    - Cache game data in local database
    - Refresh stale game data
    - Search and filter games
    - Manage game metadata

    Design Notes:
        - Service layer handles business logic
        - Repository handles data access
        - Client handles external API calls
        - Service coordinates between them
        - All methods are async

    Usage:
        >>> async with AsyncSessionLocal() as session:
        ...     steam_client = SteamClient(api_key="...")
        ...     await steam_client.start()
        ...
        ...     service = GameService(session, steam_client)
        ...     game = await service.get_or_fetch_game(730)
        ...
        ...     await steam_client.close()
    """

    def __init__(self, session: AsyncSession, steam_client: SteamClient):
        """
        Initialize GameService.

        Args:
            session: Database session
            steam_client: Steam API client (must be started)

        Example:
            >>> service = GameService(session, steam_client)
        """
        self.session = session
        self.steam_client = steam_client
        self.repo = GameRepository(session)

    async def get_or_fetch_game(
        self, app_id: int, force_refresh: bool = False
    ) -> Optional[Game]:
        """
        Get game from cache or fetch from Steam API.

        If game exists in cache and is not stale (unless force_refresh),
        return cached version. Otherwise, fetch from Steam API and cache.

        Args:
            app_id: Steam App ID
            force_refresh: Force refresh even if cached data is fresh

        Returns:
            Game object, or None if not found

        Example:
            >>> game = await service.get_or_fetch_game(730)
            >>> game.name
            'Counter-Strike: Global Offensive'
        """
        # Check if we have cached data
        if not force_refresh:
            cached_game = await self.repo.get_by_id(app_id)
            if cached_game and not cached_game.needs_refresh:
                return cached_game

        # Fetch from Steam API
        try:
            steam_data = await self.steam_client.get_app_details(app_id)
            if not steam_data:
                return None

            # Parse and save to database
            game = await self._save_game_from_steam_data(app_id, steam_data)
            await self.session.commit()

            return game

        except SteamAPIError as e:
            # Log error and return cached data if available
            print(f"Error fetching game {app_id}: {e}")
            return await self.repo.get_by_id(app_id)

    async def _save_game_from_steam_data(
        self, app_id: int, steam_data: dict
    ) -> Game:
        """
        Parse Steam API data and save to database.

        Args:
            app_id: Steam App ID
            steam_data: Raw data from Steam API

        Returns:
            Saved Game object

        Note:
            This is an internal method that parses Steam's API format.
        """
        # Extract basic info
        name = steam_data.get("name", "Unknown")
        game_type = steam_data.get("type", "game")  # game, dlc, bundle
        header_image = steam_data.get("header_image")  # Steam header image URL

        # Extract release date as ISO string (YYYY-MM-DD)
        release_date = None
        release_info = steam_data.get("release_date", {})
        if release_info.get("coming_soon") is False:
            date_str = release_info.get("date")
            if date_str:
                try:
                    # Try parsing common date formats
                    # Steam uses formats like "Jan 1, 2020" or "1 Jan, 2020"
                    from dateutil import parser
                    parsed_date = parser.parse(date_str).date()
                    # Store as ISO format string for consistent storage
                    release_date = parsed_date.isoformat()
                except Exception:
                    # If parsing fails, leave as None
                    pass

        # Check if this is a bundle
        is_bundle = game_type == "bundle"

        # Fetch review data from Steam Reviews API
        review_score = None
        total_positive = None
        total_negative = None

        if not is_bundle and game_type == "game":
            try:
                review_data = await self.steam_client.get_app_reviews(app_id)
                if review_data:
                    review_score = review_data.get("review_score")
                    total_positive = review_data.get("total_positive")
                    total_negative = review_data.get("total_negative")
                    total_reviews_from_api = review_data.get("total_reviews")
            except Exception as e:
                # If review fetch fails, continue without review data
                print(f"Failed to fetch reviews for {app_id}: {e}")
        bundle_content = None
        if is_bundle:
            # Extract bundle apps
            bundle_apps = steam_data.get("package_groups", [])
            if bundle_apps:
                # This is simplified - real implementation would parse package data
                bundle_content = []

        # Check if this is a DLC
        game_id = None  # Parent game ID for DLC
        if game_type == "dlc":
            # Steam provides "fullgame" field for DLC
            fullgame = steam_data.get("fullgame", {})
            if fullgame:
                game_id = int(fullgame.get("appid", 0)) or None

        # Check if game already exists
        existing_game = await self.repo.get_by_id(app_id)

        if existing_game:
            # Update existing game
            existing_game.name = name
            existing_game.type = game_type
            existing_game.header_image = header_image
            existing_game.release_date = release_date
            existing_game.is_bundle = is_bundle
            existing_game.bundle_content = bundle_content
            existing_game.game_id = game_id
            existing_game.review_score = review_score
            existing_game.total_positive = total_positive
            existing_game.total_negative = total_negative
            existing_game.total_reviews = total_positive + total_negative if (total_positive is not None and total_negative is not None) else None
            existing_game.last_refreshed_at = datetime.utcnow()

            return existing_game
        else:
            # Create new game
            game = await self.repo.create(
                id=app_id,
                name=name,
                type=game_type,
                header_image=header_image,
                release_date=release_date,
                is_bundle=is_bundle,
                bundle_content=bundle_content,
                game_id=game_id,
                review_score=review_score,
                total_positive=total_positive,
                total_negative=total_negative,
                total_reviews=total_positive + total_negative if (total_positive is not None and total_negative is not None) else None,
                last_refreshed_at=datetime.utcnow(),
            )

            return game

    async def refresh_stale_games(self, limit: int = 10) -> int:
        """
        Refresh stale games from Steam API.

        Fetches stale games (older than CACHE_DAYS) and updates them
        from Steam API.

        Args:
            limit: Maximum number of games to refresh

        Returns:
            Number of games refreshed

        Example:
            >>> count = await service.refresh_stale_games(limit=5)
            >>> print(f"Refreshed {count} games")
        """
        stale_games = await self.repo.get_stale_games(limit=limit)
        refreshed_count = 0

        for game in stale_games:
            try:
                steam_data = await self.steam_client.get_app_details(game.id)
                if steam_data:
                    await self._save_game_from_steam_data(game.id, steam_data)
                    refreshed_count += 1
            except SteamAPIError as e:
                print(f"Error refreshing game {game.id}: {e}")
                continue

        if refreshed_count > 0:
            await self.session.commit()

        return refreshed_count

    async def search_games(
        self, query: str, limit: Optional[int] = 20
    ) -> List[Game]:
        """
        Search cached games by name.

        Args:
            query: Search query
            limit: Maximum results to return

        Returns:
            List of matching games

        Example:
            >>> games = await service.search_games("portal")
            >>> for game in games:
            ...     print(game.name)
        """
        return await self.repo.search_by_name(query, limit=limit)

    async def get_highly_rated_games(
        self, min_score: int = 8, min_reviews: int = 1000, limit: int = 50
    ) -> List[Game]:
        """
        Get highly-rated games from cache.

        Args:
            min_score: Minimum review score (0-10)
            min_reviews: Minimum number of reviews
            limit: Maximum results to return

        Returns:
            List of highly-rated games

        Example:
            >>> games = await service.get_highly_rated_games(min_score=9)
        """
        return await self.repo.get_highly_rated(
            min_score=min_score, min_reviews=min_reviews, limit=limit
        )

    async def get_games_by_type(
        self, game_type: str, limit: Optional[int] = None
    ) -> List[Game]:
        """
        Get games by type (game, dlc, bundle).

        Args:
            game_type: Type to filter by
            limit: Maximum results to return

        Returns:
            List of games of specified type

        Example:
            >>> dlcs = await service.get_games_by_type("dlc", limit=10)
        """
        games = await self.repo.get_by_type(game_type)
        if limit:
            return games[:limit]
        return games

    async def get_game_cache_stats(self) -> dict:
        """
        Get statistics about game cache.

        Returns:
            Dictionary with cache statistics:
                - total: Total games in cache
                - by_type: Counts by game type
                - stale_count: Number of stale games needing refresh

        Example:
            >>> stats = await service.get_game_cache_stats()
            >>> print(f"Total games: {stats['total']}")
            >>> print(f"Stale games: {stats['stale_count']}")
        """
        total = await self.repo.count()

        # Count by type (count_by_type returns a dict)
        type_counts = await self.repo.count_by_type()

        # Count stale games
        stale_games = await self.repo.get_stale_games(limit=None)
        stale_count = len(stale_games)

        return {
            "total": total,
            "by_type": type_counts,
            "stale_count": stale_count,
        }

    async def bulk_cache_games(self, app_ids: List[int]) -> int:
        """
        Cache multiple games from Steam API.

        Fetches game data for all provided app IDs and caches them.
        Skips games that are already cached and fresh.

        Args:
            app_ids: List of Steam App IDs to cache

        Returns:
            Number of games cached

        Example:
            >>> cached = await service.bulk_cache_games([730, 440, 570])
            >>> print(f"Cached {cached} games")
        """
        cached_count = 0

        for app_id in app_ids:
            # Skip if already cached and fresh
            existing = await self.repo.get_by_id(app_id)
            if existing and not existing.needs_refresh:
                continue

            try:
                game = await self.get_or_fetch_game(app_id)
                if game:
                    cached_count += 1
            except Exception as e:
                print(f"Error caching game {app_id}: {e}")
                continue

        await self.session.commit()
        return cached_count
