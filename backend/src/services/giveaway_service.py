"""Giveaway service with business logic for giveaway management.

This module provides the service layer for giveaway operations, coordinating
between repositories and external SteamGifts client.
"""

from typing import Optional, List, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.giveaway import GiveawayRepository
from repositories.entry import EntryRepository
from utils.steamgifts_client import SteamGiftsClient
from core.exceptions import SteamGiftsError
from services.game_service import GameService
from models.giveaway import Giveaway
from models.entry import Entry


class GiveawayService:
    """
    Service for giveaway management.

    This service coordinates between:
    - GiveawayRepository (database)
    - EntryRepository (database)
    - SteamGiftsClient (web scraping)
    - GameService (game data)

    Handles:
    - Scraping giveaways from SteamGifts
    - Caching giveaway data
    - Entering giveaways
    - Tracking entry history
    - Filtering eligible giveaways

    Design Notes:
        - Service layer handles business logic
        - Coordinates multiple repositories and services
        - All methods are async

    Usage:
        >>> async with AsyncSessionLocal() as session:
        ...     sg_client = SteamGiftsClient(phpsessid="...", user_agent="...")
        ...     await sg_client.start()
        ...
        ...     steam_client = SteamClient(api_key="...")
        ...     await steam_client.start()
        ...
        ...     game_service = GameService(session, steam_client)
        ...     service = GiveawayService(session, sg_client, game_service)
        ...
        ...     giveaways = await service.sync_giveaways(pages=2)
    """

    def __init__(
        self,
        session: AsyncSession,
        steamgifts_client: SteamGiftsClient,
        game_service: GameService,
    ):
        """
        Initialize GiveawayService.

        Args:
            session: Database session
            steamgifts_client: SteamGifts web scraping client (must be started)
            game_service: Game service for caching game data

        Example:
            >>> service = GiveawayService(session, sg_client, game_service)
        """
        self.session = session
        self.sg_client = steamgifts_client
        self.game_service = game_service
        self.giveaway_repo = GiveawayRepository(session)
        self.entry_repo = EntryRepository(session)

    async def sync_giveaways(
        self,
        pages: int = 1,
        search_query: Optional[str] = None,
        giveaway_type: Optional[str] = None,
        dlc_only: bool = False,
        min_copies: Optional[int] = None,
    ) -> Tuple[int, int]:
        """
        Sync giveaways from SteamGifts to database.

        Fetches giveaways from SteamGifts and caches them in database.
        Also caches associated game data.

        Args:
            pages: Number of pages to fetch (default: 1)
            search_query: Optional search query
            giveaway_type: Optional type filter ("wishlist", "recommended", "new", etc.)
            dlc_only: If True, only fetch DLC giveaways
            min_copies: Minimum number of copies (e.g., 2 for multi-copy)

        Returns:
            Tuple of (new_count, updated_count)

        Example:
            >>> new, updated = await service.sync_giveaways(pages=3)
            >>> print(f"Added {new} new, updated {updated} existing")

            >>> # Sync wishlist giveaways
            >>> new, updated = await service.sync_giveaways(pages=2, giveaway_type="wishlist")

            >>> # Sync DLC giveaways
            >>> new, updated = await service.sync_giveaways(pages=2, dlc_only=True)
        """
        new_count = 0
        updated_count = 0

        for page in range(1, pages + 1):
            try:
                giveaways_data = await self.sg_client.get_giveaways(
                    page=page,
                    search_query=search_query,
                    giveaway_type=giveaway_type,
                    dlc_only=dlc_only,
                    min_copies=min_copies,
                )

                for ga_data in giveaways_data:
                    # Check if exists
                    existing = await self.giveaway_repo.get_by_code(ga_data["code"])

                    # Cache game data if we have game_id
                    if ga_data.get("game_id"):
                        try:
                            await self.game_service.get_or_fetch_game(ga_data["game_id"])
                        except Exception as e:
                            print(f"Error caching game {ga_data['game_id']}: {e}")

                    if existing:
                        # Update existing giveaway
                        await self._update_giveaway(existing, ga_data)
                        updated_count += 1
                    else:
                        # Create new giveaway
                        await self._create_giveaway(ga_data)
                        new_count += 1

            except SteamGiftsError as e:
                print(f"Error fetching page {page}: {e}")
                break

        await self.session.commit()
        return new_count, updated_count

    async def sync_wins(self, pages: int = 1) -> int:
        """
        Sync won giveaways from SteamGifts to database.

        Fetches the /giveaways/won page and marks matching giveaways as won.

        Args:
            pages: Number of pages to fetch (default: 1)

        Returns:
            Number of newly detected wins

        Example:
            >>> new_wins = await service.sync_wins(pages=2)
            >>> print(f"Found {new_wins} new wins!")
        """
        from datetime import datetime

        new_wins = 0

        for page in range(1, pages + 1):
            try:
                won_data = await self.sg_client.get_won_giveaways(page=page)

                for win in won_data:
                    # Look up giveaway by code
                    giveaway = await self.giveaway_repo.get_by_code(win["code"])

                    if giveaway and not giveaway.is_won:
                        # Mark as won
                        giveaway.is_won = True
                        giveaway.won_at = win.get("won_at") or datetime.utcnow()
                        new_wins += 1

                    elif not giveaway:
                        # Giveaway not in our database - create it as won
                        url = f"https://www.steamgifts.com/giveaway/{win['code']}/"
                        await self.giveaway_repo.create(
                            code=win["code"],
                            url=url,
                            game_name=win["game_name"],
                            price=0,  # Unknown price for historical wins
                            game_id=win.get("game_id"),
                            is_entered=True,
                            is_won=True,
                            won_at=win.get("won_at") or datetime.utcnow(),
                        )
                        new_wins += 1

            except Exception as e:
                print(f"Error fetching wins page {page}: {e}")
                break

        await self.session.commit()
        return new_wins

    async def sync_entered_giveaways(self, pages: int = 1) -> int:
        """
        Sync entered giveaways from SteamGifts to database.

        Fetches the /giveaways/entered page and marks matching giveaways
        as entered in the local database. This ensures our database
        stays in sync with what's actually entered on SteamGifts.

        Args:
            pages: Number of pages to fetch (default: 1)

        Returns:
            Number of giveaways marked as entered

        Example:
            >>> synced = await service.sync_entered_giveaways(pages=2)
            >>> print(f"Synced {synced} entered giveaways")
        """
        synced_count = 0

        for page in range(1, pages + 1):
            try:
                entered_data = await self.sg_client.get_entered_giveaways(page=page)

                for entry in entered_data:
                    # Look up giveaway by code
                    giveaway = await self.giveaway_repo.get_by_code(entry["code"])

                    if giveaway and not giveaway.is_entered:
                        # Mark as entered
                        giveaway.is_entered = True
                        giveaway.entered_at = entry.get("entered_at")
                        synced_count += 1

                    elif not giveaway:
                        # Giveaway not in our database - create it as entered
                        url = f"https://www.steamgifts.com/giveaway/{entry['code']}/"
                        await self.giveaway_repo.create(
                            code=entry["code"],
                            url=url,
                            game_name=entry["game_name"],
                            price=entry.get("price", 0),
                            game_id=entry.get("game_id"),
                            end_time=entry.get("end_time"),
                            is_entered=True,
                            entered_at=entry.get("entered_at"),
                        )
                        synced_count += 1

            except Exception as e:
                print(f"Error fetching entered page {page}: {e}")
                break

        await self.session.commit()
        return synced_count

    async def get_won_giveaways(
        self, limit: int = 50, offset: int = 0
    ) -> List[Giveaway]:
        """
        Get all won giveaways from database.

        Args:
            limit: Maximum number to return
            offset: Number of records to skip

        Returns:
            List of won giveaways, ordered by won_at (most recent first)
        """
        return await self.giveaway_repo.get_won(limit=limit, offset=offset)

    async def get_win_count(self) -> int:
        """
        Get total number of wins.

        Returns:
            Total number of won giveaways
        """
        return await self.giveaway_repo.count_won()

    async def _create_giveaway(self, ga_data: dict) -> Giveaway:
        """
        Create new giveaway from scraped data.

        Args:
            ga_data: Giveaway data from SteamGifts

        Returns:
            Created Giveaway object
        """
        # Build URL from code
        url = f"https://www.steamgifts.com/giveaway/{ga_data['code']}/"

        giveaway = await self.giveaway_repo.create(
            code=ga_data["code"],
            url=url,
            game_name=ga_data["game_name"],
            price=ga_data["price"],
            copies=ga_data.get("copies", 1),
            end_time=ga_data.get("end_time"),
            game_id=ga_data.get("game_id"),
            is_wishlist=ga_data.get("is_wishlist", False),
            is_entered=ga_data.get("is_entered", False),
        )
        return giveaway

    async def _update_giveaway(self, giveaway: Giveaway, ga_data: dict):
        """
        Update existing giveaway from scraped data.

        Args:
            giveaway: Existing giveaway object
            ga_data: New data from SteamGifts
        """
        # Update mutable fields
        giveaway.end_time = ga_data.get("end_time", giveaway.end_time)

        # Update game_id if we found it and didn't have it before
        if ga_data.get("game_id") and not giveaway.game_id:
            giveaway.game_id = ga_data["game_id"]

        # Update wishlist flag (can change from False to True, but not back)
        if ga_data.get("is_wishlist"):
            giveaway.is_wishlist = True

    async def enter_giveaway(
        self, giveaway_code: str, entry_type: str = "manual"
    ) -> Optional[Entry]:
        """
        Enter a giveaway and record the entry.

        Args:
            giveaway_code: Giveaway code to enter
            entry_type: Type of entry ("manual", "auto", "wishlist")

        Returns:
            Entry object if successful, None otherwise

        Example:
            >>> entry = await service.enter_giveaway("AbCd1", entry_type="auto")
            >>> if entry:
            ...     print(f"Entered! Spent {entry.points_spent} points")
        """
        # Get giveaway
        giveaway = await self.giveaway_repo.get_by_code(giveaway_code)
        if not giveaway:
            print(f"Giveaway {giveaway_code} not found in database")
            return None

        # Check if already entered
        existing_entry = await self.entry_repo.get_by_giveaway(giveaway.id)
        if existing_entry:
            print(f"Already entered giveaway {giveaway_code}")
            return existing_entry

        # Try to enter
        try:
            success = await self.sg_client.enter_giveaway(giveaway_code)

            if success:
                # Mark as entered
                await self.giveaway_repo.mark_entered(giveaway.id)

                # Create entry record
                entry = await self.entry_repo.create(
                    giveaway_id=giveaway.id,
                    points_spent=giveaway.price,
                    entry_type=entry_type,
                    status="success",
                )
                await self.session.commit()

                return entry
            else:
                # Entry failed
                entry = await self.entry_repo.create(
                    giveaway_id=giveaway.id,
                    points_spent=0,
                    entry_type=entry_type,
                    status="failed",
                    error_message="SteamGifts returned failure",
                )
                await self.session.commit()

                return None

        except SteamGiftsError as e:
            # Record failed entry
            entry = await self.entry_repo.create(
                giveaway_id=giveaway.id,
                points_spent=0,
                entry_type=entry_type,
                status="failed",
                error_message=str(e),
            )
            await self.session.commit()

            print(f"Error entering giveaway {giveaway_code}: {e}")
            return None

    async def get_eligible_giveaways(
        self,
        min_price: int = 0,
        max_price: Optional[int] = None,
        min_score: Optional[int] = None,
        min_reviews: Optional[int] = None,
        max_game_age: Optional[int] = None,
        limit: int = 50,
    ) -> List[Giveaway]:
        """
        Get eligible giveaways based on criteria.

        Filters active giveaways that:
        - Haven't been entered yet
        - Aren't hidden
        - Meet price criteria
        - Meet game rating criteria (if specified)
        - Meet game age criteria (if specified)

        Args:
            min_price: Minimum giveaway price
            max_price: Maximum giveaway price
            min_score: Minimum game review score (0-10)
            min_reviews: Minimum number of reviews
            max_game_age: Maximum game age in years (None = no limit)
            limit: Maximum results to return

        Returns:
            List of eligible giveaways

        Example:
            >>> eligible = await service.get_eligible_giveaways(
            ...     min_price=50,
            ...     max_price=200,
            ...     min_score=8,
            ...     max_game_age=5,
            ...     limit=10
            ... )
        """
        giveaways = await self.giveaway_repo.get_eligible(
            min_price=min_price,
            max_price=max_price,
            min_score=min_score,
            min_reviews=min_reviews,
            max_game_age=max_game_age,
            limit=limit,
        )

        return giveaways

    async def get_active_giveaways(
        self, limit: Optional[int] = None, offset: int = 0, min_score: Optional[int] = None,
        is_safe: Optional[bool] = None
    ) -> List[Giveaway]:
        """
        Get all active (non-expired) giveaways.

        Args:
            limit: Maximum number to return
            offset: Number of records to skip (for pagination)
            min_score: Minimum review score (0-10) to filter by
            is_safe: Filter by safety status (True=safe only, False=unsafe only, None=all)

        Returns:
            List of active giveaways

        Example:
            >>> active = await service.get_active_giveaways(limit=20, offset=40, min_score=7, is_safe=True)
        """
        return await self.giveaway_repo.get_active(limit=limit, offset=offset, min_score=min_score, is_safe=is_safe)

    async def get_all_giveaways(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> List[Giveaway]:
        """
        Get all giveaways (including expired ones).

        Args:
            limit: Maximum number to return
            offset: Number of records to skip (for pagination)

        Returns:
            List of all giveaways

        Example:
            >>> all_giveaways = await service.get_all_giveaways(limit=20, offset=0)
        """
        return await self.giveaway_repo.get_all(limit=limit, offset=offset)

    async def get_entered_giveaways(
        self, limit: Optional[int] = None, active_only: bool = False
    ) -> List[Giveaway]:
        """
        Get entered giveaways.

        Args:
            limit: Maximum number to return
            active_only: If True, only return non-expired giveaways

        Returns:
            List of entered giveaways

        Example:
            >>> entered = await service.get_entered_giveaways(limit=20, active_only=True)
        """
        return await self.giveaway_repo.get_entered(limit=limit, active_only=active_only)

    async def get_expiring_soon(
        self, hours: int = 24, limit: Optional[int] = None
    ) -> List[Giveaway]:
        """
        Get giveaways expiring within specified hours.

        Args:
            hours: Number of hours
            limit: Maximum number to return

        Returns:
            List of giveaways expiring soon

        Example:
            >>> expiring = await service.get_expiring_soon(hours=6, limit=10)
        """
        return await self.giveaway_repo.get_expiring_soon(hours=hours, limit=limit)

    async def enrich_giveaways_with_game_data(
        self, giveaways: List[Giveaway]
    ) -> List[Giveaway]:
        """
        Enrich giveaways with game data (thumbnail, reviews).

        For each giveaway with a game_id, fetches the Game data and populates:
        - game_thumbnail: Steam header image URL
        - game_review_score: Review score (0-10)
        - game_total_reviews: Total number of reviews
        - game_review_summary: Text summary ("Overwhelmingly Positive", etc.)

        Args:
            giveaways: List of giveaway objects to enrich

        Returns:
            The same list of giveaways, enriched with game data

        Example:
            >>> giveaways = await service.get_active_giveaways(limit=10)
            >>> enriched = await service.enrich_giveaways_with_game_data(giveaways)
        """
        for giveaway in giveaways:
            if not giveaway.game_id:
                continue

            # Fetch game data (from cache or Steam API)
            try:
                game = await self.game_service.get_or_fetch_game(giveaway.game_id)
                if not game:
                    continue
            except Exception:
                # Game fetch failed, skip enrichment for this giveaway
                continue

            # Set thumbnail URL (from stored header_image or fallback to CDN URL)
            giveaway.game_thumbnail = (
                game.header_image or
                f"https://cdn.cloudflare.steamstatic.com/steam/apps/{game.id}/header.jpg"
            )

            # Set review data
            giveaway.game_review_score = game.review_score
            giveaway.game_total_reviews = game.total_reviews

            # Generate review summary based on score and review count
            if game.review_score is not None and game.total_reviews is not None:
                giveaway.game_review_summary = self._generate_review_summary(
                    game.review_score, game.total_reviews
                )

        return giveaways

    def _generate_review_summary(
        self, review_score: int, total_reviews: int
    ) -> str:
        """
        Generate Steam-style review summary text.

        Args:
            review_score: Review score (0-10 scale)
            total_reviews: Total number of reviews

        Returns:
            Summary text like "Overwhelmingly Positive", "Mixed", etc.

        Example:
            >>> service._generate_review_summary(9, 50000)
            'Overwhelmingly Positive'
        """
        # Convert 0-10 scale to percentage
        percentage = review_score * 10

        # Not enough reviews
        if total_reviews < 10:
            return "Not Enough Reviews"

        # Determine sentiment based on Steam's algorithm
        # https://partner.steamgames.com/doc/store/reviews
        if total_reviews >= 500:
            # High review count - can be "Overwhelmingly" tier
            if percentage >= 95:
                return "Overwhelmingly Positive"
            elif percentage >= 80:
                return "Very Positive"
            elif percentage >= 70:
                return "Positive"
            elif percentage >= 40:
                return "Mixed"
            elif percentage >= 20:
                return "Negative"
            else:
                return "Overwhelmingly Negative"
        else:
            # Lower review count - regular tiers only
            if percentage >= 80:
                return "Very Positive"
            elif percentage >= 70:
                return "Positive"
            elif percentage >= 40:
                return "Mixed"
            elif percentage >= 20:
                return "Negative"
            else:
                return "Very Negative"

    async def hide_giveaway(self, giveaway_code: str) -> bool:
        """
        Hide a giveaway from future recommendations.

        Args:
            giveaway_code: Giveaway code to hide

        Returns:
            True if hidden, False if not found

        Example:
            >>> await service.hide_giveaway("AbCd1")
        """
        giveaway = await self.giveaway_repo.get_by_code(giveaway_code)
        if not giveaway:
            return False

        await self.giveaway_repo.hide_giveaway(giveaway.id)
        await self.session.commit()
        return True

    async def unhide_giveaway(self, giveaway_code: str) -> bool:
        """
        Unhide a previously hidden giveaway.

        Args:
            giveaway_code: Giveaway code to unhide

        Returns:
            True if unhidden, False if not found

        Example:
            >>> await service.unhide_giveaway("AbCd1")
        """
        giveaway = await self.giveaway_repo.get_by_code(giveaway_code)
        if not giveaway:
            return False

        await self.giveaway_repo.unhide_giveaway(giveaway.id)
        await self.session.commit()
        return True

    async def remove_entry(self, giveaway_code: str) -> bool:
        """
        Remove an entry for a giveaway.

        This marks the giveaway as not entered and deletes the entry record.

        Args:
            giveaway_code: Code of the giveaway to remove entry from

        Returns:
            True if entry was removed, False if not found or not entered

        Example:
            >>> removed = await service.remove_entry("AbCd1")
            >>> if removed:
            ...     print("Entry removed successfully")
        """
        giveaway = await self.giveaway_repo.get_by_code(giveaway_code)
        if not giveaway:
            return False

        if not giveaway.is_entered:
            return False

        # Find the entry
        entry = await self.entry_repo.get_by_giveaway(giveaway.id)
        if entry:
            # Delete the entry
            await self.entry_repo.delete(entry.id)

        # Mark giveaway as not entered
        giveaway.is_entered = False
        giveaway.entered_at = None
        await self.session.commit()

        return True

    async def search_giveaways(
        self, query: str, limit: Optional[int] = 20
    ) -> List[Giveaway]:
        """
        Search giveaways by game name.

        Args:
            query: Search query
            limit: Maximum results to return

        Returns:
            List of matching giveaways

        Example:
            >>> results = await service.search_giveaways("portal")
        """
        return await self.giveaway_repo.search_by_game_name(query, limit=limit)

    async def get_entry_history(
        self, limit: int = 50, status: Optional[str] = None
    ) -> List[Entry]:
        """
        Get entry history.

        Args:
            limit: Maximum results to return
            status: Filter by status ("success", "failed", "pending")

        Returns:
            List of entries

        Example:
            >>> history = await service.get_entry_history(limit=20)
            >>> for entry in history:
            ...     print(f"Spent {entry.points_spent} points")
        """
        if status:
            return await self.entry_repo.get_by_status(status, limit=limit)
        else:
            return await self.entry_repo.get_recent(limit=limit)

    async def get_entry_stats(self) -> dict:
        """
        Get comprehensive entry statistics.

        Returns:
            Dictionary with entry statistics

        Example:
            >>> stats = await service.get_entry_stats()
            >>> print(f"Success rate: {stats['success_rate']:.1f}%")
        """
        return await self.entry_repo.get_stats()

    async def get_giveaway_stats(self) -> dict:
        """
        Get giveaway statistics.

        Returns:
            Dictionary with giveaway statistics:
                - total: Total giveaways in database
                - active: Active (non-expired) giveaways
                - entered: Giveaways we've entered
                - hidden: Hidden giveaways
                - wins: Total wins
                - win_rate: Win rate percentage

        Example:
            >>> stats = await service.get_giveaway_stats()
            >>> print(f"Active giveaways: {stats['active']}")
        """
        total = await self.giveaway_repo.count()
        active = await self.giveaway_repo.count_active()
        entered = await self.giveaway_repo.count_entered()
        hidden = len(await self.giveaway_repo.get_hidden())
        wins = await self.giveaway_repo.count_won()
        win_rate = (wins / entered * 100) if entered > 0 else 0.0

        return {
            "total": total,
            "active": active,
            "entered": entered,
            "hidden": hidden,
            "wins": wins,
            "win_rate": win_rate,
        }

    async def get_current_points(self) -> int:
        """
        Get current user points from SteamGifts.

        Returns:
            Current points balance

        Raises:
            SteamGiftsError: If unable to fetch points

        Example:
            >>> points = await service.get_current_points()
            >>> print(f"Current points: {points}P")
        """
        try:
            return await self.sg_client.get_user_points()
        except SteamGiftsError as e:
            # If we can't fetch points, return 0 rather than failing
            print(f"Failed to fetch current points: {e}")
            return 0

    async def check_giveaway_safety(self, giveaway_code: str) -> dict:
        """
        Check if a giveaway is safe to enter (trap detection).

        Analyzes the giveaway page content for warning signs that might
        indicate a trap or scam giveaway (e.g., "don't enter", "ban", "fake").

        Args:
            giveaway_code: Giveaway code to check

        Returns:
            Dictionary with safety check results:
                - is_safe: True if giveaway appears safe
                - safety_score: Confidence score (0-100)
                - details: List of found warning words

        Example:
            >>> safety = await service.check_giveaway_safety("AbCd1")
            >>> if not safety['is_safe']:
            ...     print(f"Warning: {safety['details']}")
        """
        # Check safety via client
        safety_result = await self.sg_client.check_giveaway_safety(giveaway_code)

        # Update giveaway in database with safety info
        giveaway = await self.giveaway_repo.get_by_code(giveaway_code)
        if giveaway:
            giveaway.is_safe = safety_result["is_safe"]
            giveaway.safety_score = safety_result["safety_score"]
            await self.session.commit()

        return safety_result

    async def hide_on_steamgifts(self, giveaway_code: str) -> bool:
        """
        Hide a game on SteamGifts (removes from all future giveaway lists).

        This sends a request to SteamGifts to hide all giveaways for the
        game associated with this giveaway. Also marks the giveaway as
        hidden in the local database.

        Args:
            giveaway_code: Giveaway code to hide

        Returns:
            True if hidden successfully, False otherwise

        Example:
            >>> success = await service.hide_on_steamgifts("AbCd1")
            >>> if success:
            ...     print("Game hidden on SteamGifts")
        """
        # Get the game_id for this giveaway
        game_id = await self.sg_client.get_giveaway_game_id(giveaway_code)

        if not game_id:
            print(f"Could not get game_id for giveaway {giveaway_code}")
            return False

        # Hide on SteamGifts
        try:
            await self.sg_client.hide_giveaway(game_id)
        except SteamGiftsError as e:
            print(f"Failed to hide on SteamGifts: {e}")
            return False

        # Also hide locally
        giveaway = await self.giveaway_repo.get_by_code(giveaway_code)
        if giveaway:
            giveaway.is_hidden = True
            await self.session.commit()

        return True

    async def post_comment(
        self, giveaway_code: str, comment_text: str = "Thanks!"
    ) -> bool:
        """
        Post a comment on a giveaway.

        Args:
            giveaway_code: Giveaway code
            comment_text: Comment text to post

        Returns:
            True if comment posted successfully, False otherwise

        Example:
            >>> success = await service.post_comment("AbCd1", "Thanks!")
            >>> if success:
            ...     print("Comment posted!")
        """
        try:
            return await self.sg_client.post_comment(giveaway_code, comment_text)
        except SteamGiftsError as e:
            print(f"Failed to post comment: {e}")
            return False

    async def enter_giveaway_with_safety_check(
        self, giveaway_code: str, entry_type: str = "auto"
    ) -> Optional[Entry]:
        """
        Enter a giveaway with safety check.

        Checks if the giveaway is safe before entering. If unsafe,
        the giveaway is hidden instead of entered.

        Args:
            giveaway_code: Giveaway code to enter
            entry_type: Type of entry ("manual", "auto", "wishlist")

        Returns:
            Entry object if successful, None if failed or unsafe

        Example:
            >>> entry = await service.enter_giveaway_with_safety_check("AbCd1")
            >>> if entry:
            ...     print("Entered safely!")
        """
        # First check safety
        try:
            safety = await self.check_giveaway_safety(giveaway_code)

            if not safety["is_safe"]:
                print(f"Giveaway {giveaway_code} is unsafe: {safety['details']}")

                # Try to hide it on SteamGifts
                await self.hide_on_steamgifts(giveaway_code)

                # Record failed entry with reason
                giveaway = await self.giveaway_repo.get_by_code(giveaway_code)
                if giveaway:
                    await self.entry_repo.create(
                        giveaway_id=giveaway.id,
                        points_spent=0,
                        entry_type=entry_type,
                        status="failed",
                        error_message=f"Unsafe giveaway: {', '.join(safety['details'])}",
                    )
                    await self.session.commit()

                return None

        except Exception as e:
            print(f"Safety check failed for {giveaway_code}: {e}")
            # Continue without safety check if it fails

        # Proceed with normal entry
        return await self.enter_giveaway(giveaway_code, entry_type)
