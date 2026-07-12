"""Giveaway service with business logic for giveaway management.

This module provides the service layer for giveaway operations, coordinating
between repositories and the external SteamGifts client. The implementation is
split by concern across three mixins; this class is the single public facade:

- :class:`services.giveaway_sync.GiveawaySyncMixin` — scrape -> cache sync steps
- :class:`services.giveaway_entry.GiveawayEntryMixin` — entering + safety + hide
- :class:`services.giveaway_query.GiveawayQueryMixin` — listings, stats, eligibility
"""

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.entry import EntryRepository
from repositories.giveaway import GiveawayRepository
from services.game_service import GameService
from services.giveaway_entry import GiveawayEntryMixin
from services.giveaway_query import GiveawayQueryMixin
from services.giveaway_sync import GiveawaySyncMixin
from utils.steamgifts_client import SteamGiftsClient


class GiveawayService(GiveawaySyncMixin, GiveawayEntryMixin, GiveawayQueryMixin):
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
        - Implementation lives in the three mixins listed in the module docstring

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
