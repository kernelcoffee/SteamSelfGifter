"""Read-side methods of GiveawayService: listings, search, stats, the
auto-join decision cycle and previews, and API-response enrichment."""

from collections import Counter
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ConfigurationError
from core.time import utcnow
from models.entry import Entry
from models.game import Game
from models.giveaway import Giveaway
from models.settings import Settings
from repositories.entry import EntryRepository
from repositories.giveaway import GiveawayRepository
from services.eligibility import (
    AutoJoinPolicy,
    Decision,
    Detail,
    InvalidPolicyError,
    PolicyFields,
    count_codes,
    decide,
    order_candidates,
    plan_cycle,
    policy_from_settings,
)
from services.game_service import GameService
from services.settings_service import INVALID_STORED_POLICY_CODE

logger = structlog.get_logger()


@dataclass(frozen=True)
class CycleCandidate:
    """An enter candidate of the cycle and the code the plan recorded for it."""

    giveaway: Giveaway
    decision: Decision
    planned: str


@dataclass
class CycleResult:
    """What one automation cycle's decision step produced.

    ``candidates``: every enter candidate in entry order, before the budget
    and the cap (the entry loop applies both with the balance actually
    spent), each with the code the plan recorded. ``counts``: stored decision
    codes over the pool. ``total``: pool size.
    """

    candidates: list[CycleCandidate]
    counts: dict[str, int]
    total: int

    def counts_after(self, outcomes: list[tuple[Giveaway, str, Detail]]) -> dict[str, int]:
        """The pool's counts once the entry loop's outcomes replace the plan's.

        Args:
            outcomes: one (giveaway, code, detail) per candidate, in candidate order.
        """
        counts = Counter(self.counts)
        for candidate, (_, code, _) in zip(self.candidates, outcomes, strict=True):
            counts[candidate.planned] -= 1
            counts[code] += 1
        return {code: n for code, n in counts.items() if n > 0}


@dataclass
class PolicyPreview:
    """A dry run of a policy over a pool; nothing is persisted.

    ``candidates``: enter candidates in entry order, sliced by offset/limit.
    ``count``: every enter candidate before slicing. ``pool``: giveaways
    evaluated. ``counts``: live decision codes over the pool (sum = pool).
    """

    candidates: list[tuple[Giveaway, Decision]]
    count: int
    pool: int
    counts: dict[str, int]


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

    async def _decide_pool(
        self, pool: list[Giveaway], policy: AutoJoinPolicy
    ) -> tuple[list[tuple[Giveaway, Decision]], list[tuple[Giveaway, Decision]], dict[int, Game]]:
        """Decide every giveaway of a price-descending pool (cache-only games).

        Returns every (giveaway, decision) in pool order, the enter
        candidates in entry order and the cached games the pool references
        (one query, reused by the preview's enrichment). Writes nothing.
        """
        now = utcnow()
        games = await self.game_service.repo.get_by_ids([g.game_id for g in pool if g.game_id])
        decided = [
            (giveaway, decide(giveaway, games.get(giveaway.game_id) if giveaway.game_id else None, policy, now))
            for giveaway in pool
        ]
        return decided, order_candidates(decided, policy, now), games

    async def decide_cycle(self, policy: AutoJoinPolicy, points: int | None) -> CycleResult:
        """
        Decide the whole candidate pool for one automation cycle and record it.

        Every active, not-entered giveaway (hidden included) gets
        ``eligibility_reason``, ``eligibility_detail`` and
        ``eligibility_checked_at`` in one commit, including the budget
        outcomes of :func:`services.eligibility.plan_cycle`, so stored
        decisions never go stale on quiet cycles. Sends nothing to SteamGifts.

        Args:
            policy: the saved auto-join policy.
            points: the current balance, or None when it could not be fetched
                (the budget is then not applied and nothing is planned).

        Returns:
            The enter candidates in entry order with their planned codes, the
            per-code counts and the pool size.
        """
        pool = await self.giveaway_repo.get_active_unentered()
        decided, ordered, _games = await self._decide_pool(pool, policy)
        plan = plan_cycle(ordered, points, policy)
        planned = {giveaway.id: (code, detail) for giveaway, code, detail in plan}

        now = utcnow()
        for giveaway, decision in decided:
            code, detail = planned.get(giveaway.id, (decision.code, decision.detail))
            giveaway.eligibility_reason = code
            giveaway.eligibility_detail = detail
            giveaway.eligibility_checked_at = now
        await self.session.commit()

        # Developer observability (not the user-facing ActivityLog): a one-line
        # breakdown of the pool's decisions this cycle (codes only).
        counts = count_codes(giveaway.eligibility_reason or "unknown" for giveaway, _ in decided)
        logger.info("eligibility_evaluated", total=len(pool), **counts)

        candidates = [
            CycleCandidate(giveaway=giveaway, decision=decision, planned=code)
            for (giveaway, decision), (_, code, _) in zip(ordered, plan, strict=True)
        ]
        return CycleResult(candidates=candidates, counts=counts, total=len(pool))

    async def record_outcomes(self, outcomes: list[tuple[Giveaway, str, Detail]]) -> None:
        """
        Record what the entry loop actually did, in one commit.

        The plan assumes every attempt succeeds; the loop follows the balance
        actually spent, so its outcomes (eligible for an attempt,
        budget_floor, cycle_cap) replace the plan's.

        Args:
            outcomes: (giveaway, code, detail) triples.
        """
        if not outcomes:
            return
        now = utcnow()
        for giveaway, code, detail in outcomes:
            giveaway.eligibility_reason = code
            giveaway.eligibility_detail = detail
            giveaway.eligibility_checked_at = now
        await self.session.commit()

    def saved_policy(self, settings: Settings, override: PolicyFields | None = None) -> AutoJoinPolicy:
        """
        Build the auto-join policy for a preview or the lens.

        Args:
            settings: the saved settings row (budget fields, and the seven
                policy fields unless ``override`` is given).
            override: an unsaved policy (POST /giveaways/preview); the stored
                priority list is then not parsed.

        Raises:
            ConfigurationError: when the priority list or a genre list in use
                cannot be parsed (CONFIG_002, naming the column).
        """
        try:
            return policy_from_settings(settings, override)
        except InvalidPolicyError as e:
            raise ConfigurationError(str(e), code=INVALID_STORED_POLICY_CODE) from e

    async def preview_policy(
        self,
        policy: AutoJoinPolicy,
        *,
        limit: int,
        offset: int = 0,
        pool: list[Giveaway] | None = None,
    ) -> PolicyPreview:
        """
        Dry-run a policy: the enter candidates in entry order, persisting nothing.

        No points fetch and no budget (the budget and the per-cycle cap apply
        at cycle time), no SteamGifts or Steam request, and no column
        attribute written on any row (the request session commits when it
        ends). The returned candidates carry the transient game fields from
        the cache the decisions already read (null when the game is not
        cached), so no second games query is needed.

        Args:
            policy: the policy to evaluate.
            limit: maximum candidates returned.
            offset: candidates skipped (lens pagination).
            pool: the giveaways to evaluate; None = the cycle's pool (active,
                not entered, hidden included). Re-sorted price descending then
                id ascending, the cycle pool's order, so equal-price
                candidates come out in the order the cycle enters them.

        Returns:
            The sliced candidates, their total, the pool size and the counts.
        """
        rows = await self.giveaway_repo.get_active_unentered() if pool is None else pool
        rows = sorted(rows, key=lambda giveaway: (-giveaway.price, giveaway.id))
        decided, ordered, games = await self._decide_pool(rows, policy)
        candidates = ordered[offset:offset + limit]
        for giveaway, _ in candidates:
            game = games.get(giveaway.game_id) if giveaway.game_id else None
            if game is not None:
                self._apply_game(giveaway, game)
        return PolicyPreview(
            candidates=candidates,
            count=len(ordered),
            pool=len(rows),
            counts=count_codes(decision.code for _, decision in decided),
        )

    async def get_unentered_giveaways(self, limit: int = 50, offset: int = 0) -> list[Giveaway]:
        """
        Browse active giveaways not entered and not hidden; no policy applied.

        Args:
            limit: Maximum number to return
            offset: Number of records to skip

        Returns:
            Active, not entered, not hidden giveaways, most expensive first
        """
        return await self.giveaway_repo.get_active_unentered(
            exclude_hidden=True, limit=limit, offset=offset
        )

    async def get_active_giveaways(
        self, limit: int | None = None, offset: int = 0, min_score: int | None = None,
        is_safe: bool | None = None, min_chance: float | None = None,
        ending_within_minutes: int | None = None, exclude_entered: bool = False,
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
            exclude_entered: Leave entered giveaways out (the auto-join lens pool)

        Returns:
            List of active giveaways

        Example:
            >>> active = await service.get_active_giveaways(limit=20, offset=40, min_score=7, is_safe=True)
        """
        return await self.giveaway_repo.get_active(
            limit=limit, offset=offset, min_score=min_score, is_safe=is_safe,
            min_chance=min_chance, ending_within_minutes=ending_within_minutes,
            exclude_entered=exclude_entered,
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
        - game_genres: Steam genres (None when not fetched yet)
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

            self._apply_game(giveaway, game)

        return giveaways

    def _apply_game(self, giveaway: Giveaway, game: Game) -> None:
        """Set the transient (never persisted) game fields on a giveaway."""
        # Thumbnail URL (stored header_image or the CDN fallback)
        giveaway.game_thumbnail = (
            game.header_image or
            f"https://cdn.cloudflare.steamstatic.com/steam/apps/{game.id}/header.jpg"
        )
        giveaway.game_genres = game.genres

        # Review data
        giveaway.game_review_score = game.review_score
        giveaway.game_total_reviews = game.total_reviews

        # Review summary based on score and review count
        if game.review_score is not None and game.total_reviews is not None:
            giveaway.game_review_summary = self._generate_review_summary(
                game.review_score, game.total_reviews
            )

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
