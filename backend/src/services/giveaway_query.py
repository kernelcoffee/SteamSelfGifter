"""Read-side methods of GiveawayService: listings, search, stats, autojoin
eligibility selection, and API-response enrichment."""

from collections import Counter

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from core.time import utcnow
from models.entry import Entry
from models.giveaway import Giveaway
from repositories.entry import EntryRepository
from repositories.giveaway import GiveawayRepository
from services.eligibility import ELIGIBLE, EligibilityCriteria, evaluate_eligibility
from services.game_service import GameService

logger = structlog.get_logger()


class GiveawayQueryMixin:
    """Giveaway Querymethods of GiveawayService (see services.giveaway_service).

    Mixin: expects the attributes declared below to be set by the composing
    class's ``__init__`` (services.giveaway_service.GiveawayService).
    """

    session: AsyncSession
    game_service: GameService
    giveaway_repo: GiveawayRepository
    entry_repo: EntryRepository

    async def get_won_giveaways(
        self, limit: int = 50, offset: int = 0
    ) -> list[Giveaway]:
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

    async def get_eligible_giveaways(
        self,
        min_price: int = 0,
        max_price: int | None = None,
        min_score: int | None = None,
        min_reviews: int | None = None,
        max_game_age: int | None = None,
        limit: int = 50,
        wishlist_priority: bool = True,
    ) -> list[Giveaway]:
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
            wishlist_priority=wishlist_priority,
        )

        return giveaways

    async def evaluate_and_get_eligible(
        self, criteria: EligibilityCriteria, limit: int | None = None
    ) -> list[Giveaway]:
        """
        Evaluate every active candidate, record why each one did or didn't qualify,
        and return the eligible giveaways (highest price first, optionally limited).

        This is the decision step for the automation/process cycle. Every active,
        not-entered giveaway gets ``eligibility_reason`` and ``eligibility_checked_at``
        persisted, so the UI can show why a giveaway wasn't entered. The returned
        set is identical to :meth:`get_eligible_giveaways` for the same criteria —
        only the recorded reasons are new (see :mod:`services.eligibility`).

        Args:
            criteria: the active autojoin thresholds.
            limit: maximum number of eligible giveaways to return (None = all).

        Returns:
            Eligible giveaways, wishlist first, then by price descending.
        """
        now = utcnow()
        candidates = await self.giveaway_repo.get_active_unentered()

        games = await self.game_service.repo.get_by_ids(
            [g.game_id for g in candidates if g.game_id]
        )

        eligible: list[Giveaway] = []
        for giveaway in candidates:
            game = games.get(giveaway.game_id) if giveaway.game_id else None
            reason = evaluate_eligibility(giveaway, game, criteria, now)
            giveaway.eligibility_reason = reason
            giveaway.eligibility_checked_at = now
            if reason == ELIGIBLE:
                eligible.append(giveaway)

        await self.session.commit()

        # Developer observability (not the user-facing ActivityLog): a one-line
        # breakdown of why the candidate pool did/didn't qualify this cycle.
        counts = Counter(g.eligibility_reason or "unknown" for g in candidates)
        logger.info("eligibility_evaluated", total=len(candidates), **dict(counts))

        # candidates are ordered by price desc; the stable sort moves wishlist
        # giveaways to the front while keeping price order within each group.
        if criteria.wishlist_priority:
            eligible.sort(key=lambda g: not g.is_wishlist)
        return eligible[:limit] if limit else eligible

    async def get_active_giveaways(
        self, limit: int | None = None, offset: int = 0, min_score: int | None = None,
        is_safe: bool | None = None, min_chance: float | None = None,
        ending_within_minutes: int | None = None,
    ) -> list[Giveaway]:
        """
        Get all active (non-expired) giveaways.

        Args:
            limit: Maximum number to return
            offset: Number of records to skip (for pagination)
            min_score: Minimum review score (0-10) to filter by
            is_safe: Filter by safety status (True=safe only, False=unsafe only, None=all)
            min_chance: Minimum win chance in percent (copies/entries*100)
            ending_within_minutes: Only giveaways ending within this many minutes

        Returns:
            List of active giveaways

        Example:
            >>> active = await service.get_active_giveaways(limit=20, offset=40, min_score=7, is_safe=True)
        """
        return await self.giveaway_repo.get_active(
            limit=limit, offset=offset, min_score=min_score, is_safe=is_safe,
            min_chance=min_chance, ending_within_minutes=ending_within_minutes,
        )

    async def get_all_giveaways(
        self, limit: int | None = None, offset: int = 0
    ) -> list[Giveaway]:
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
        self, limit: int | None = None, active_only: bool = False
    ) -> list[Giveaway]:
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
        self, hours: int = 24, limit: int | None = None
    ) -> list[Giveaway]:
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
        self, giveaways: list[Giveaway]
    ) -> list[Giveaway]:
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
        self, query: str, limit: int | None = 20
    ) -> list[Giveaway]:
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
        self, limit: int = 50, status: str | None = None
    ) -> list[Entry]:
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
