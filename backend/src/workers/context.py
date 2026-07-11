"""Shared bootstrap for worker jobs.

Every automation job needs the same setup: a DB session, started SteamGifts and
Steam HTTP clients, and the services built on top of them. Rather than repeat
that block in every worker, jobs open a single async context manager:

    async with automation_context() as ctx:
        if not ctx.authenticated:
            return {"skipped": True, "reason": "not_authenticated"}
        await ctx.giveaway_service.sync_giveaways(...)
    # clients + session are closed automatically

When no PHPSESSID is configured the context still yields, but with
``authenticated`` False and the services left as ``None`` (no HTTP clients are
started). Callers should check ``ctx.authenticated`` before touching services.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import AsyncSessionLocal
from services.game_service import GameService
from services.giveaway_service import GiveawayService
from services.notification_service import NotificationService
from services.scheduler_service import SchedulerService
from services.settings_service import SettingsService
from utils.steam_client import SteamClient
from utils.steamgifts_client import SteamGiftsClient

logger = structlog.get_logger()


@dataclass
class AutomationContext:
    """Ready-to-use session, settings and services for a worker job.

    When the user is not authenticated, only ``session``, ``settings`` and
    ``settings_service`` are populated; the rest are ``None``.
    """

    session: AsyncSession
    settings: object
    settings_service: SettingsService
    game_service: GameService | None = None
    giveaway_service: GiveawayService | None = None
    notification_service: NotificationService | None = None
    scheduler_service: SchedulerService | None = None

    @property
    def authenticated(self) -> bool:
        """True when a PHPSESSID is configured and services are ready."""
        return bool(self.settings and self.settings.phpsessid)


@asynccontextmanager
async def automation_context() -> AsyncIterator[AutomationContext]:
    """Open a DB session and (if authenticated) the full service stack.

    Yields an :class:`AutomationContext`. HTTP clients are started on entry and
    always closed on exit. If no PHPSESSID is set, no clients are started and the
    context is yielded with ``authenticated`` False.
    """
    async with AsyncSessionLocal() as session:
        settings_service = SettingsService(session)
        settings = await settings_service.get_settings()

        if not settings.phpsessid:
            yield AutomationContext(
                session=session,
                settings=settings,
                settings_service=settings_service,
            )
            return

        sg_client = SteamGiftsClient(
            phpsessid=settings.phpsessid,
            user_agent=settings.user_agent,
        )
        await sg_client.start()

        steam_client = SteamClient()
        await steam_client.start()

        game_service = GameService(session=session, steam_client=steam_client)
        giveaway_service = GiveawayService(
            session=session,
            steamgifts_client=sg_client,
            game_service=game_service,
        )
        notification_service = NotificationService(session=session)
        scheduler_service = SchedulerService(
            session=session, giveaway_service=giveaway_service
        )

        try:
            yield AutomationContext(
                session=session,
                settings=settings,
                settings_service=settings_service,
                game_service=game_service,
                giveaway_service=giveaway_service,
                notification_service=notification_service,
                scheduler_service=scheduler_service,
            )
        finally:
            await sg_client.close()
            await steam_client.close()
