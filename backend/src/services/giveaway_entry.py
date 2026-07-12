"""Entry-side methods of GiveawayService: entering giveaways (with optional
inline safety check), safety scoring, hiding on SteamGifts, comments, points."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import SteamGiftsError
from models.entry import Entry
from repositories.entry import EntryRepository
from repositories.giveaway import GiveawayRepository
from utils.steamgifts_client import SteamGiftsClient

logger = structlog.get_logger()


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
                logger.warning("giveaway_unsafe", code=giveaway_code, details=safety["details"])

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
            logger.error("safety_check_failed", code=giveaway_code, error=str(e))
            # Continue without safety check if it fails

        # Proceed with normal entry
        return await self.enter_giveaway(giveaway_code, entry_type)

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
