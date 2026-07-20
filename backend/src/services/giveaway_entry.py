"""Entry-side methods of GiveawayService: entering giveaways (with optional
inline safety check), safety scoring, hiding on SteamGifts, comments, points."""

import asyncio
import random
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import SteamGiftsError
from core.time import utcnow
from models.entry import Entry
from models.giveaway import Giveaway
from repositories.entry import EntryRepository
from repositories.giveaway import GiveawayRepository
from utils import steamgifts_parser as parser
from utils.steamgifts_client import SteamGiftsClient

logger = structlog.get_logger()

# Stored safety verdicts younger than this are trusted at entry time without
# refetching the giveaway page (the background sweep keeps them fresh).
SAFETY_RECHECK_HOURS = 24


class GiveawayEntryMixin:
    """Giveaway Entrymethods of GiveawayService (see services.giveaway_service).

    Mixin: expects the attributes declared below to be set by the composing
    class's ``__init__`` (services.giveaway_service.GiveawayService).
    """

    session: AsyncSession
    sg_client: SteamGiftsClient
    giveaway_repo: GiveawayRepository
    entry_repo: EntryRepository

    async def enter_giveaway(
        self, giveaway_code: str, entry_type: str = "manual"
    ) -> Entry | None:
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
            logger.warning("giveaway_not_found", code=giveaway_code)
            return None

        # Check if already entered
        existing_entry = await self.entry_repo.get_by_giveaway(giveaway.id)
        if existing_entry:
            logger.info("giveaway_already_entered", code=giveaway_code)
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

            logger.error("giveaway_entry_error", code=giveaway_code, error=str(e))
            return None

    async def enter_giveaway_with_safety_check(
        self, giveaway_code: str, entry_type: str = "auto"
    ) -> Entry | None:
        """
        Enter a giveaway with safety check.

        Uses the stored safety verdict when fresh (see SAFETY_RECHECK_HOURS),
        otherwise checks the giveaway page. Outcomes: "safe" enters normally;
        "borderline" skips without hiding (left for manual review); "unsafe"
        hides the giveaway on SteamGifts. A failing safety check skips the
        giveaway this cycle (fail closed).

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
        # Fail closed: a safety check that errors skips the giveaway for this
        # cycle (it stays eligible and is retried next cycle) instead of
        # entering unchecked.
        try:
            safety = await self._current_safety(giveaway_code)
        except Exception as e:
            logger.warning("safety_check_failed_skipping", code=giveaway_code, error=str(e))
            return None

        verdict = safety.get("verdict", "safe" if safety["is_safe"] else "unsafe")

        if verdict == "unsafe":
            logger.warning("giveaway_unsafe", code=giveaway_code, details=safety["details"])
            await self.hide_on_steamgifts(giveaway_code)
            await self._record_safety_rejection(
                giveaway_code,
                entry_type,
                f"Unsafe giveaway (score {safety['safety_score']}): "
                f"{', '.join(safety['details'])}",
            )
            return None

        if verdict == "borderline":
            # Suspicious but not certain: skip without hiding so the giveaway
            # stays visible for manual review. is_safe=False keeps it out of
            # future eligible pools.
            logger.warning(
                "giveaway_borderline_skipped",
                code=giveaway_code,
                score=safety["safety_score"],
                details=safety["details"],
            )
            await self._record_safety_rejection(
                giveaway_code,
                entry_type,
                f"Borderline safety score {safety['safety_score']}, "
                "skipped for manual review",
            )
            return None

        # Proceed with normal entry
        return await self.enter_giveaway(giveaway_code, entry_type)

    async def _current_safety(self, giveaway_code: str) -> dict[str, Any]:
        """Return a safety verdict, reusing a fresh stored one when possible."""
        giveaway = await self.giveaway_repo.get_by_code(giveaway_code)
        if (
            giveaway is not None
            and giveaway.is_safe is not None
            and giveaway.safety_checked_at is not None
            and utcnow() - giveaway.safety_checked_at < timedelta(hours=SAFETY_RECHECK_HOURS)
        ):
            return self._verdict_from_stored(giveaway)
        return await self.check_giveaway_safety(giveaway_code)

    @staticmethod
    def _verdict_from_stored(giveaway: Giveaway) -> dict[str, Any]:
        """Rebuild a verdict dict from the persisted safety fields."""
        score = giveaway.safety_score or 0
        if giveaway.is_safe:
            verdict = "safe"
        elif score >= parser.UNSAFE_THRESHOLD:
            verdict = "borderline"
        else:
            verdict = "unsafe"
        return {
            "verdict": verdict,
            "is_safe": bool(giveaway.is_safe),
            "safety_score": score,
            "details": [],
            "warning_comments": 0,
            "cached": True,
        }

    async def _record_safety_rejection(
        self, giveaway_code: str, entry_type: str, reason: str
    ) -> None:
        """Record a failed entry documenting why safety blocked this giveaway."""
        giveaway = await self.giveaway_repo.get_by_code(giveaway_code)
        if giveaway:
            await self.entry_repo.create(
                giveaway_id=giveaway.id,
                points_spent=0,
                entry_type=entry_type,
                status="failed",
                error_message=reason,
            )
            await self.session.commit()

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
            giveaway.safety_checked_at = utcnow()
            await self.session.commit()

        return safety_result

    async def sweep_unchecked_safety(
        self, limit: int = 10, delay_min: float = 1.0, delay_max: float = 3.0
    ) -> dict[str, int]:
        """Safety-check a batch of unchecked active giveaways (background sweep).

        Fetches up to ``limit`` giveaways that have never been checked
        (``is_safe`` NULL), oldest-expiring first, scores each page, and hides
        outright traps — so most giveaways carry a stored verdict before the
        entry loop ever considers them. A short random delay between page
        fetches keeps the traffic pattern polite.

        Returns:
            Counts: ``{"checked", "safe", "borderline", "unsafe", "errors"}``.
        """
        unchecked = await self.giveaway_repo.get_unchecked_eligible(limit=limit)
        counts = {"checked": 0, "safe": 0, "borderline": 0, "unsafe": 0, "errors": 0}

        for index, giveaway in enumerate(unchecked):
            if index:
                await asyncio.sleep(random.uniform(delay_min, delay_max))

            try:
                result = await self.check_giveaway_safety(giveaway.code)
            except Exception as e:
                counts["errors"] += 1
                logger.warning("safety_sweep_check_failed", code=giveaway.code, error=str(e))
                continue

            counts["checked"] += 1
            verdict = result.get("verdict", "safe" if result["is_safe"] else "unsafe")
            counts[verdict] += 1

            if verdict == "unsafe":
                logger.warning(
                    "safety_sweep_unsafe", code=giveaway.code, details=result["details"]
                )
                await self.hide_on_steamgifts(giveaway.code)

        return counts

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
            logger.warning("game_id_lookup_failed", code=giveaway_code)
            return False

        # Hide on SteamGifts
        try:
            await self.sg_client.hide_giveaway(game_id)
        except SteamGiftsError as e:
            logger.error("steamgifts_hide_failed", code=giveaway_code, error=str(e))
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
            logger.error("comment_post_failed", code=giveaway_code, error=str(e))
            return False

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
            logger.error("points_fetch_failed", error=str(e))
            return 0
