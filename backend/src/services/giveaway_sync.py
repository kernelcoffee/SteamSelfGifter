"""Scrape -> cache sync steps of GiveawayService (regular/wishlist/DLC pages,
wins, entered giveaways)."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import SteamGiftsError
from core.time import utcnow
from models.giveaway import Giveaway
from repositories.giveaway import GiveawayRepository
from services.game_service import GameService
from utils.steamgifts_client import SteamGiftsClient

logger = structlog.get_logger()


class GiveawaySyncMixin:
    """Giveaway Syncmethods of GiveawayService (see services.giveaway_service).

    Mixin: expects the attributes declared below to be set by the composing
    class's ``__init__`` (services.giveaway_service.GiveawayService).
    """

    session: AsyncSession
    sg_client: SteamGiftsClient
    game_service: GameService
    giveaway_repo: GiveawayRepository

    async def sync_giveaways(
        self,
        pages: int = 1,
        search_query: str | None = None,
        giveaway_type: str | None = None,
        dlc_only: bool = False,
        min_copies: int | None = None,
    ) -> tuple[int, int]:
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
                            logger.error("game_cache_failed", game_id=ga_data["game_id"], error=str(e))

                    if existing:
                        # Update existing giveaway
                        await self._update_giveaway(existing, ga_data)
                        updated_count += 1
                    else:
                        # Create new giveaway
                        await self._create_giveaway(ga_data)
                        new_count += 1

            except SteamGiftsError as e:
                logger.error("giveaway_page_fetch_failed", page=page, error=str(e))
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
                        giveaway.won_at = win.get("won_at") or utcnow()
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
                            won_at=win.get("won_at") or utcnow(),
                        )
                        new_wins += 1

            except Exception as e:
                logger.error("wins_page_fetch_failed", page=page, error=str(e))
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
                logger.error("entered_page_fetch_failed", page=page, error=str(e))
                break

        await self.session.commit()
        return synced_count

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

    async def _update_giveaway(self, giveaway: Giveaway, ga_data: dict) -> None:
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
