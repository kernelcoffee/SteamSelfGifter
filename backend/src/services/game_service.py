"""Game service with business logic for game data management.

This module provides the service layer for game operations, coordinating
between the GameRepository and external Steam API client.
"""

import math
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog
from dateutil import parser as date_parser
from sqlalchemy.ext.asyncio import AsyncSession

from core.time import utcnow
from models.game import Game
from repositories.game import GameRepository
from utils.steam_client import SteamAPIError, SteamAPIRateLimitError, SteamClient

logger = structlog.get_logger()

# How long Steam lookups are suspended after a rate-limit error. Steam's
# store throttle (429, or HTTP 200 with a null body) usually lasts a few
# minutes; every request sent inside it extends it.
STEAM_RATE_LIMIT_COOLDOWN_SECONDS = 180.0


class SteamCooldown:
    """Process-wide pause on Steam store lookups after a rate-limit error.

    GameService instances live for one request or one worker job, but
    Steam's throttle is per IP, so the pause is shared by all of them
    through the module-level ``steam_cooldown``. While it is active,
    ``get_or_fetch_game`` serves the cache without calling Steam and
    ``refresh_stale_games`` does nothing. Uses a monotonic clock so it is
    unaffected by wall-clock changes.
    """

    def __init__(self, seconds: float):
        self.seconds = seconds
        self._until: float | None = None

    @property
    def active(self) -> bool:
        """Whether Steam lookups are currently suspended."""
        return self._until is not None and time.monotonic() < self._until

    @property
    def remaining_seconds(self) -> int:
        """Whole seconds left in the pause (rounded up), 0 when inactive."""
        if self._until is None:
            return 0
        return max(0, math.ceil(self._until - time.monotonic()))

    def trip(self) -> None:
        """Start (or restart) the pause after a rate-limit error."""
        self._until = time.monotonic() + self.seconds

    def reset(self) -> None:
        """Clear the pause."""
        self._until = None


steam_cooldown = SteamCooldown(STEAM_RATE_LIMIT_COOLDOWN_SECONDS)


class FetchStatus(StrEnum):
    """Outcome of one attempt to fetch a game from Steam."""

    REFRESHED = "refreshed"  # Steam answered; the row was saved
    UNAVAILABLE = "unavailable"  # Steam does not serve this app
    RATE_LIMITED = "rate_limited"  # skipped or stopped by Steam's throttle
    FAILED = "failed"  # any other Steam API error


@dataclass(frozen=True, slots=True)
class RefreshOutcome:
    """Result of an explicit refresh (``GameService.refresh_game``).

    ``game`` is the row after the attempt (the cached one when nothing was
    refreshed, None when the app is neither cached nor served by Steam);
    ``retry_after_seconds`` is set only for RATE_LIMITED.
    """

    status: FetchStatus
    game: Game | None
    retry_after_seconds: int | None = None

    @property
    def refreshed(self) -> bool:
        return self.status is FetchStatus.REFRESHED


def _descriptions(items: Any) -> list[str]:
    """Extract the ``description`` strings from a Steam genres/categories list.

    Steam sends ``[{"id": ..., "description": "Action"}, ...]`` (genre ids are
    strings, category ids ints; neither is kept). Anything that is not a list
    yields []; items that are not dicts or whose description is missing,
    not a string or blank are skipped. Steam's order is kept.
    """
    if not isinstance(items, list):
        return []
    return [
        item["description"]
        for item in items
        if isinstance(item, dict)
        and isinstance(item.get("description"), str)
        and item["description"].strip()
    ]


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
    ) -> Game | None:
        """
        Get game from cache or fetch from Steam API.

        If game exists in cache and is not outdated by age (unless
        force_refresh), return cached version. Otherwise, fetch from Steam API
        and cache. A recent row whose genres were never fetched (cached before
        genres were stored) is served as is: this runs once per giveaway in
        sync and enrichment, so treating those rows as stale here would refetch
        the whole legacy cache in one burst. ``refresh_stale_games``, run with
        a small limit every automation cycle, backfills them instead.

        Args:
            app_id: Steam App ID
            force_refresh: Force refresh even if cached data is fresh

        Returns:
            Game object, or None if the app is neither cached nor served
            by Steam. A cached row is returned even when Steam reports the
            app unavailable or is rate limiting us.

        Example:
            >>> game = await service.get_or_fetch_game(730)
            >>> game.name
            'Counter-Strike: Global Offensive'
        """
        game, _status = await self.lookup_game(app_id, force_refresh=force_refresh)
        return game

    async def lookup_game(
        self, app_id: int, force_refresh: bool = False
    ) -> tuple[Game | None, FetchStatus | None]:
        """
        Same lookup as ``get_or_fetch_game``, also saying how the row was got.

        For callers that must tell "Steam does not serve this app" from
        "Steam was not asked because it is rate limiting us" when no row
        comes back (``GET /games/{app_id}`` answers 404 for the first and
        429 for the second).

        Args:
            app_id: Steam App ID
            force_refresh: Force refresh even if cached data is fresh

        Returns:
            The row (or None) and the fetch status, which is None when the
            row was served from the cache without a Steam lookup.
        """
        cached_game = await self.repo.get_by_id(app_id)
        if cached_game and not force_refresh and not cached_game.is_stale_by_age:
            return cached_game, None

        return await self._fetch_from_steam(app_id, cached_game)

    def steam_retry_after_seconds(self) -> int:
        """
        Seconds left in the shared Steam rate-limit cool-down, 0 when none.

        While it is above 0, Steam lookups are skipped (``get_or_fetch_game``
        serves the cache, ``refresh_stale_games`` returns 0 at once), so
        callers can report a skip instead of an empty result.
        """
        return steam_cooldown.remaining_seconds

    async def refresh_game(self, app_id: int) -> RefreshOutcome:
        """
        Explicitly refresh one game from Steam, reporting what happened.

        Unlike ``get_or_fetch_game(force_refresh=True)``, which always hands
        back the best row it has, this tells the caller whether Steam was
        actually reached: during the rate-limit cool-down, or when this very
        request is throttled (on appdetails, or on appreviews after the
        appdetails fields were saved), the status is RATE_LIMITED with the
        seconds left, so a row is never presented as freshly refreshed when
        part of it was not.

        Args:
            app_id: Steam App ID

        Returns:
            RefreshOutcome with the status, the row and, when rate limited,
            ``retry_after_seconds``.
        """
        cached_game = await self.repo.get_by_id(app_id)
        game, status = await self._fetch_from_steam(app_id, cached_game)
        retry_after = (
            self.steam_retry_after_seconds() if status is FetchStatus.RATE_LIMITED else None
        )
        return RefreshOutcome(status=status, game=game, retry_after_seconds=retry_after)

    async def _fetch_from_steam(
        self, app_id: int, cached_game: Game | None
    ) -> tuple[Game | None, FetchStatus]:
        """Fetch one app from Steam and save it, falling back to the cache.

        Returns the row to serve (the cached one when nothing was saved,
        None when the app is neither cached nor served) and the status.
        """
        if steam_cooldown.active:
            # Steam throttled us recently: serve whatever is cached (possibly
            # stale, or genres not fetched yet) rather than extend the ban.
            logger.debug("game_fetch_skipped_rate_limited", app_id=app_id)
            return cached_game, FetchStatus.RATE_LIMITED

        try:
            steam_data = await self.steam_client.get_app_details(app_id)
            if not steam_data:
                # Not available on Steam (delisted, region-locked, invalid).
                # Record the check on a cached row so it is not refetched on
                # every call, and keep serving that row (thumbnail, reviews).
                # Only an app that was never cached is "not found".
                if cached_game:
                    self._mark_unavailable(cached_game)
                    await self.session.commit()
                return cached_game, FetchStatus.UNAVAILABLE

            game, reviews_rate_limited = await self._store_steam_data(app_id, steam_data)
            await self.session.commit()
            if reviews_rate_limited:
                # appdetails was saved but appreviews was throttled: the
                # reviews are not fresh and an existing row kept its old
                # refresh time, so this is not a completed refresh.
                return game, FetchStatus.RATE_LIMITED
            return game, FetchStatus.REFRESHED

        except SteamAPIRateLimitError as e:
            steam_cooldown.trip()
            logger.warning("game_fetch_rate_limited", app_id=app_id, error=str(e))
            return await self.repo.get_by_id(app_id), FetchStatus.RATE_LIMITED
        except SteamAPIError as e:
            # Log error and return cached data if available
            logger.error("game_fetch_failed", app_id=app_id, error=str(e))
            return await self.repo.get_by_id(app_id), FetchStatus.FAILED

    @staticmethod
    def _mark_unavailable(game: Game) -> None:
        """Record that Steam had no data for a cached game.

        Bumps ``last_refreshed_at`` so the row moves to the back of the stale
        queue, and stores [] for genres/categories that were never fetched:
        Steam has none to give for this app, and leaving them NULL would keep
        the row permanently in the background refresh queue (see
        Game.needs_refresh), retried every automation cycle. So [] on a game
        means "Steam returned none" or "Steam does not serve this app"; both
        pass the genre exclusion, as NULL does. Genres already fetched are kept. The row is retried by the
        normal 7-day rule, which fills the lists if the app comes back.
        """
        game.last_refreshed_at = utcnow()
        if game.genres is None:
            game.genres = []
        if game.categories is None:
            game.categories = []

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
            This is an internal method that parses Steam's API format. Use
            ``_store_steam_data`` when the caller must know whether the
            appreviews call was rate limited.
        """
        game, _reviews_rate_limited = await self._store_steam_data(app_id, steam_data)
        return game

    async def _store_steam_data(
        self, app_id: int, steam_data: dict
    ) -> tuple[Game, bool]:
        """
        Parse Steam API data, fetch reviews for games, and save the row.

        Args:
            app_id: Steam App ID
            steam_data: Raw ``data`` dict from Steam's appdetails

        Returns:
            The saved Game and whether the appreviews call was rate limited
            (the appdetails fields were saved, the reviews were not refreshed,
            an existing row kept its ``last_refreshed_at`` and the shared
            ``steam_cooldown`` was started).
        """
        # Extract basic info
        name = steam_data.get("name", "Unknown")
        game_type = steam_data.get("type", "game")  # game, dlc, bundle
        header_image = steam_data.get("header_image")  # Steam header image URL

        # Genres and categories, for every type. A missing key means Steam
        # has none ([]), never None (None is reserved for "not fetched yet").
        genres = _descriptions(steam_data.get("genres", []))
        categories = _descriptions(steam_data.get("categories", []))

        # Extract release date as ISO string (YYYY-MM-DD)
        release_date = None
        release_info = steam_data.get("release_date", {})
        if release_info.get("coming_soon") is False:
            date_str = release_info.get("date")
            if date_str:
                try:
                    # Steam uses formats like "Jan 1, 2020" or "1 Jan, 2020";
                    # store as ISO format string for consistent storage.
                    release_date = date_parser.parse(date_str).date().isoformat()
                except (ValueError, OverflowError):
                    # Unparseable date ("Coming soon", "Q3 2026", ...) → None
                    pass

        # Check if this is a bundle
        is_bundle = game_type == "bundle"

        # Fetch review data from Steam Reviews API (0 = no reviews / unknown,
        # matching the non-nullable Game columns).
        review_score = 0
        total_positive = 0
        total_negative = 0
        # Set when the appreviews call raised: an existing row then keeps its
        # cached review data instead of having it overwritten with zeros.
        review_fetch_failed = False
        review_rate_limited = False

        if not is_bundle and game_type == "game":
            try:
                review_data = await self.steam_client.get_app_reviews(app_id)
                if review_data:
                    review_score = review_data.get("review_score") or 0
                    total_positive = review_data.get("total_positive") or 0
                    total_negative = review_data.get("total_negative") or 0
            except Exception as e:
                # If review fetch fails, continue without fresh review data
                review_fetch_failed = True
                if isinstance(e, SteamAPIRateLimitError):
                    review_rate_limited = True
                    steam_cooldown.trip()
                logger.warning("game_review_fetch_failed", app_id=app_id, error=str(e))
        bundle_content: list | None = None
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

        total_reviews = total_positive + total_negative

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
            if not review_fetch_failed:
                existing_game.review_score = review_score
                existing_game.total_positive = total_positive
                existing_game.total_negative = total_negative
                existing_game.total_reviews = total_reviews
            existing_game.genres = genres
            existing_game.categories = categories
            if not review_rate_limited:
                # A throttled review fetch leaves the refresh time alone, so
                # a row that was stale by age is retried (reviews included)
                # once the cool-down ends instead of waiting 7 more days.
                existing_game.last_refreshed_at = utcnow()

            return existing_game, review_rate_limited
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
                total_reviews=total_reviews,
                genres=genres,
                categories=categories,
                last_refreshed_at=utcnow(),
            )

            return game, review_rate_limited

    async def refresh_stale_games(self, limit: int = 10) -> int:
        """
        Refresh stale games from Steam API.

        Fetches stale games (older than CACHE_DAYS, or whose genres were
        never fetched) oldest first and updates them from Steam API. A game
        Steam no longer serves is marked checked (see ``_mark_unavailable``)
        so it rotates to the back of the queue. The batch stops at the first
        rate-limit error, keeping what was already saved: retrying the rest
        inside a throttled window only extends it; it also starts the shared
        ``steam_cooldown``, during which this method returns 0 at once.

        Args:
            limit: Maximum number of games to refresh

        Returns:
            Number of games refreshed

        Example:
            >>> count = await service.refresh_stale_games(limit=5)
            >>> print(f"Refreshed {count} games")
        """
        if steam_cooldown.active:
            logger.info("game_refresh_skipped_rate_limited")
            return 0

        stale_games = await self.repo.get_stale_games(limit=limit)
        refreshed_count = 0
        changed = False

        for game in stale_games:
            try:
                steam_data = await self.steam_client.get_app_details(game.id)
            except SteamAPIRateLimitError as e:
                steam_cooldown.trip()
                logger.warning("game_refresh_rate_limited", game_id=game.id, error=str(e))
                break
            except SteamAPIError as e:
                logger.error("game_refresh_failed", game_id=game.id, error=str(e))
                continue

            changed = True
            if not steam_data:
                self._mark_unavailable(game)
                continue

            _saved, reviews_rate_limited = await self._store_steam_data(game.id, steam_data)
            if reviews_rate_limited:
                # appreviews was throttled inside the save (which started the
                # cool-down): keep the appdetails fields already stored and
                # stop here, as for a throttled appdetails call. The row keeps
                # its refresh time, so it is not counted as refreshed.
                break
            refreshed_count += 1

        if changed:
            await self.session.commit()

        return refreshed_count

    async def get_genre_counts(self) -> list[dict[str, Any]]:
        """
        Get the distinct Steam genres across cached games with their counts.

        Returns:
            ``[{"name": str, "count": int}, ...]`` sorted by count descending
            then name ascending; games whose genres are NULL or [] are ignored.

        Example:
            >>> await service.get_genre_counts()
            [{"name": "Action", "count": 2}, {"name": "Indie", "count": 1}]
        """
        rows = await self.repo.count_genres()
        return [{"name": name, "count": count} for name, count in rows]

    async def search_games(
        self, query: str, limit: int = 20
    ) -> list[Game]:
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
    ) -> list[Game]:
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
        self, game_type: str, limit: int | None = None
    ) -> list[Game]:
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

    async def bulk_cache_games(self, app_ids: list[int]) -> int:
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
            # Skip if already cached and fresh (same age rule as
            # get_or_fetch_game, which would serve it from the cache anyway)
            existing = await self.repo.get_by_id(app_id)
            if existing and not existing.is_stale_by_age:
                continue

            try:
                game = await self.get_or_fetch_game(app_id)
                if game:
                    cached_count += 1
            except Exception as e:
                logger.error("game_cache_failed", app_id=app_id, error=str(e))
                continue

        await self.session.commit()
        return cached_count
