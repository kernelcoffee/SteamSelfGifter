"""Background safety check worker.

Low-priority job that checks giveaway safety at a slow rate to avoid
triggering rate limits on SteamGifts. Processes one giveaway at a time.
"""

from typing import Dict, Any

import structlog

from db.session import AsyncSessionLocal
from services.giveaway_service import GiveawayService
from services.game_service import GameService
from services.settings_service import SettingsService
from services.notification_service import NotificationService
from repositories.giveaway import GiveawayRepository
from utils.steamgifts_client import SteamGiftsClient
from utils.steam_client import SteamClient

logger = structlog.get_logger()


async def safety_check_cycle() -> Dict[str, Any]:
    """
    Run a safety check on one unchecked eligible giveaway.

    This job is designed to run frequently (e.g., every 30-60 seconds) but
    only processes one giveaway per run to avoid rate limiting.

    Returns:
        Dictionary with check results:
            - checked: Number of giveaways checked (0 or 1)
            - safe: Number found safe
            - unsafe: Number found unsafe
            - skipped: Whether check was skipped
            - reason: Reason for skip if applicable

    Example:
        >>> results = await safety_check_cycle()
        >>> if results['checked']:
        ...     print(f"Checked 1 giveaway: safe={results['safe']}")
    """
    results = {
        "checked": 0,
        "safe": 0,
        "unsafe": 0,
        "skipped": False,
        "reason": None,
    }

    async with AsyncSessionLocal() as session:
        # Check settings
        settings_service = SettingsService(session)
        settings = await settings_service.get_settings()

        # Skip if not authenticated
        if not settings.phpsessid:
            logger.debug("safety_check_skipped", reason="not_authenticated")
            results["skipped"] = True
            results["reason"] = "not_authenticated"
            return results

        # Skip if safety check is disabled
        if not settings.safety_check_enabled:
            logger.debug("safety_check_skipped", reason="disabled")
            results["skipped"] = True
            results["reason"] = "safety_check_disabled"
            return results

        # Get one unchecked giveaway
        giveaway_repo = GiveawayRepository(session)
        unchecked = await giveaway_repo.get_unchecked_eligible(limit=1)

        if not unchecked:
            logger.debug("safety_check_skipped", reason="no_unchecked_giveaways")
            results["skipped"] = True
            results["reason"] = "no_unchecked_giveaways"
            return results

        giveaway = unchecked[0]

        # Create clients
        sg_client = SteamGiftsClient(
            phpsessid=settings.phpsessid,
            user_agent=settings.user_agent,
        )
        await sg_client.start()

        steam_client = SteamClient()
        await steam_client.start()

        try:
            # Create service
            game_service = GameService(session=session, steam_client=steam_client)
            giveaway_service = GiveawayService(
                session=session,
                steamgifts_client=sg_client,
                game_service=game_service,
            )

            # Run safety check
            logger.info(
                "safety_check_running",
                giveaway_code=giveaway.code,
                game_name=giveaway.game_name,
            )

            safety_result = await giveaway_service.check_giveaway_safety(giveaway.code)

            results["checked"] = 1

            # Create notification service for logging
            notification_service = NotificationService(session=session)

            if safety_result["is_safe"]:
                results["safe"] = 1
                logger.info(
                    "safety_check_passed",
                    giveaway_code=giveaway.code,
                    safety_score=safety_result["safety_score"],
                )
            else:
                results["unsafe"] = 1
                logger.warning(
                    "safety_check_failed",
                    giveaway_code=giveaway.code,
                    safety_score=safety_result["safety_score"],
                    details=safety_result.get("details", []),
                )

                # Log the unsafe giveaway to activity log
                details_str = ", ".join(safety_result.get("details", []))
                await notification_service.log_activity(
                    level="warning",
                    event_type="safety",
                    message=f"Unsafe giveaway detected: {giveaway.game_name} ({details_str})",
                    details={
                        "code": giveaway.code,
                        "game_name": giveaway.game_name,
                        "safety_score": safety_result["safety_score"],
                        "issues": safety_result.get("details", []),
                    }
                )

                # Hide unsafe giveaway on SteamGifts
                try:
                    await giveaway_service.hide_on_steamgifts(giveaway.code)
                    logger.info(
                        "unsafe_giveaway_hidden",
                        giveaway_code=giveaway.code,
                    )
                    await notification_service.log_activity(
                        level="info",
                        event_type="safety",
                        message=f"Hidden unsafe giveaway on SteamGifts: {giveaway.game_name}",
                        details={"code": giveaway.code, "game_name": giveaway.game_name}
                    )
                except Exception as e:
                    logger.warning(
                        "hide_unsafe_giveaway_failed",
                        giveaway_code=giveaway.code,
                        error=str(e),
                    )
                    await notification_service.log_activity(
                        level="error",
                        event_type="safety",
                        message=f"Failed to hide unsafe giveaway: {giveaway.game_name}",
                        details={"code": giveaway.code, "error": str(e)}
                    )

        except Exception as e:
            logger.error(
                "safety_check_error",
                giveaway_code=giveaway.code,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Mark as checked but with unknown status to avoid retrying indefinitely
            giveaway.is_safe = True  # Assume safe on error to not block entry
            giveaway.safety_score = 50  # Middle score to indicate uncertainty
            await session.commit()

        finally:
            await sg_client.close()
            await steam_client.close()

    return results