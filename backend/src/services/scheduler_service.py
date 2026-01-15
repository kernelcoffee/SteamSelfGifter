"""Scheduler service with business logic for automation management.

This module provides the service layer for scheduler operations, coordinating
between repositories and giveaway entry automation.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from repositories.settings import SettingsRepository
from repositories.giveaway import GiveawayRepository
from services.giveaway_service import GiveawayService
from models.scheduler_state import SchedulerState
from workers.scheduler import scheduler_manager

# Job ID for the win check job
WIN_CHECK_JOB_ID = "win_check"


class SchedulerService:
    """
    Service for scheduler and automation management.

    This service coordinates between:
    - SchedulerState model (database)
    - SettingsRepository (configuration)
    - GiveawayService (giveaway entry logic)

    Handles:
    - Running automation cycles
    - Tracking scheduler state and statistics
    - Managing entry limits

    Design Notes:
        - Service layer handles business logic
        - Coordinates multiple repositories and services
        - All methods are async
        - Runtime state (is_running, is_paused) managed by APScheduler

    Usage:
        >>> async with AsyncSessionLocal() as session:
        ...     giveaway_service = GiveawayService(...)
        ...     service = SchedulerService(session, giveaway_service)
        ...     await service.run_automation_cycle()
    """

    def __init__(
        self,
        session: AsyncSession,
        giveaway_service: GiveawayService,
    ):
        """
        Initialize SchedulerService.

        Args:
            session: Database session
            giveaway_service: GiveawayService for entering giveaways

        Example:
            >>> service = SchedulerService(session, giveaway_service)
        """
        self.session = session
        self.giveaway_service = giveaway_service
        self.settings_repo = SettingsRepository(session)
        self.giveaway_repo = GiveawayRepository(session)

    async def _get_or_create_state(self) -> SchedulerState:
        """
        Get or create scheduler state (singleton).

        Returns:
            SchedulerState object (id=1)
        """
        result = await self.session.execute(
            select(SchedulerState).where(SchedulerState.id == 1)
        )
        state = result.scalar_one_or_none()

        if not state:
            state = SchedulerState(id=1)
            self.session.add(state)
            await self.session.flush()

        return state

    async def run_automation_cycle(self) -> Dict[str, Any]:
        """
        Run one automation cycle.

        This is the main automation logic that:
        1. Syncs giveaways from SteamGifts
        2. Filters eligible giveaways
        3. Enters giveaways within limits
        4. Updates state and statistics

        Returns:
            Dictionary with cycle statistics:
                - synced: Number of giveaways synced
                - eligible: Number of eligible giveaways
                - entered: Number of giveaways entered
                - failed: Number of failed entries
                - points_spent: Total points spent

        Example:
            >>> results = await service.run_automation_cycle()
            >>> print(f"Entered {results['entered']} giveaways")
        """
        settings = await self.settings_repo.get_settings()
        state = await self._get_or_create_state()

        # Track statistics
        stats = {
            "synced": 0,
            "eligible": 0,
            "entered": 0,
            "failed": 0,
            "points_spent": 0,
        }

        try:
            # Sync wishlist giveaways first (higher priority)
            wishlist_new, wishlist_updated = await self.giveaway_service.sync_giveaways(
                pages=2,  # Wishlist usually has fewer pages
                giveaway_type="wishlist",
                safety_check_enabled=settings.safety_check_enabled,
            )

            # Sync regular giveaways
            new, updated = await self.giveaway_service.sync_giveaways(
                pages=settings.max_scan_pages or 3,
                safety_check_enabled=settings.safety_check_enabled,
            )
            stats["synced"] = new + updated + wishlist_new + wishlist_updated

            # Get eligible giveaways
            eligible = await self.giveaway_service.get_eligible_giveaways(
                min_price=settings.autojoin_min_price or 0,
                max_price=None,  # No max price limit
                min_score=settings.autojoin_min_score,
                min_reviews=settings.autojoin_min_reviews,
                limit=settings.max_entries_per_cycle or 10,
            )
            stats["eligible"] = len(eligible)

            # Enter eligible giveaways
            entered_count = 0
            failed_count = 0

            max_entries = settings.max_entries_per_cycle or 10

            for giveaway in eligible[:max_entries]:
                # Try to enter
                entry = await self.giveaway_service.enter_giveaway(
                    giveaway.code,
                    entry_type="auto"
                )

                if entry:
                    entered_count += 1
                    stats["points_spent"] += entry.points_spent
                else:
                    failed_count += 1

            stats["entered"] = entered_count
            stats["failed"] = failed_count

            # Update state statistics
            state.last_scan_at = datetime.utcnow()
            state.total_scans += 1
            state.total_entries += entered_count

            await self.session.commit()

            # Schedule win check for newly entered giveaways
            if entered_count > 0:
                await self.schedule_next_win_check()

        except Exception as e:
            # Record error
            state.total_errors += 1
            await self.session.commit()
            raise e

        return stats

    async def get_scheduler_stats(self) -> Dict[str, Any]:
        """
        Get scheduler statistics.

        Returns:
            Dictionary with scheduler stats:
                - total_scans: Total scans completed
                - total_entries: Total giveaways entered
                - total_errors: Total errors encountered
                - last_scan_at: Last scan time
                - next_scan_at: Next scheduled scan time
                - has_run: Whether scheduler has ever run
                - time_since_last_scan: Seconds since last scan

        Example:
            >>> stats = await service.get_scheduler_stats()
            >>> print(f"Total entries: {stats['total_entries']}")
        """
        state = await self._get_or_create_state()

        return {
            "total_scans": state.total_scans,
            "total_entries": state.total_entries,
            "total_errors": state.total_errors,
            "last_scan_at": state.last_scan_at,
            "next_scan_at": state.next_scan_at,
            "has_run": state.has_run,
            "time_since_last_scan": state.time_since_last_scan,
            "time_until_next_scan": state.time_until_next_scan,
        }

    async def update_next_scan_time(self, next_scan_at: datetime) -> SchedulerState:
        """
        Update the next scheduled scan time.

        Args:
            next_scan_at: When next scan is scheduled (UTC)

        Returns:
            Updated SchedulerState object

        Example:
            >>> from datetime import datetime, timedelta
            >>> next_time = datetime.utcnow() + timedelta(minutes=30)
            >>> await service.update_next_scan_time(next_time)
        """
        state = await self._get_or_create_state()
        state.next_scan_at = next_scan_at
        await self.session.commit()
        return state

    async def reset_scheduler_stats(self) -> SchedulerState:
        """
        Reset scheduler statistics to zero.

        Useful for testing or starting fresh.
        Clears all counters and timestamps.

        Returns:
            Reset SchedulerState object

        Example:
            >>> state = await service.reset_scheduler_stats()
            >>> state.total_scans
            0
        """
        state = await self._get_or_create_state()

        # Reset all statistics
        state.last_scan_at = None
        state.next_scan_at = None
        state.total_scans = 0
        state.total_entries = 0
        state.total_errors = 0

        await self.session.commit()

        return state

    def start_automation(self) -> None:
        """
        Start the scheduler for automation.

        Starts the APScheduler instance. Does nothing if already running.

        Example:
            >>> service.start_automation()
        """
        scheduler_manager.start()

    def stop_automation(self, wait: bool = True) -> None:
        """
        Stop the scheduler.

        Args:
            wait: If True, wait for running jobs to complete

        Example:
            >>> service.stop_automation()
        """
        scheduler_manager.stop(wait=wait)

    def pause_automation(self) -> None:
        """
        Pause all scheduled jobs.

        Jobs remain scheduled but won't execute until resumed.

        Example:
            >>> service.pause_automation()
        """
        scheduler_manager.pause()

    def resume_automation(self) -> None:
        """
        Resume paused automation.

        Example:
            >>> service.resume_automation()
        """
        scheduler_manager.resume()

    def get_scheduler_status(self) -> Dict[str, Any]:
        """
        Get combined scheduler status.

        Returns status from the APScheduler instance including
        running state, paused state, and job information.

        Returns:
            Dictionary with scheduler status:
                - running: Whether scheduler is running
                - paused: Whether scheduler is paused
                - job_count: Number of scheduled jobs
                - jobs: List of job information

        Example:
            >>> status = service.get_scheduler_status()
            >>> print(f"Running: {status['running']}")
        """
        return scheduler_manager.get_status()

    def is_automation_running(self) -> bool:
        """
        Check if automation is currently running.

        Returns:
            True if scheduler is running and not paused

        Example:
            >>> if service.is_automation_running():
            ...     print("Automation active")
        """
        return scheduler_manager.is_running and not scheduler_manager.is_paused

    async def schedule_next_win_check(self) -> Optional[datetime]:
        """
        Schedule a win check job for when the next entered giveaway expires.

        This implements smart win-check scheduling:
        - Only creates a job for the soonest-expiring entered giveaway
        - On trigger, recalculates for the next job
        - If no entered giveaways, removes any existing job

        Returns:
            The scheduled datetime, or None if no giveaways to check

        Example:
            >>> next_check = await service.schedule_next_win_check()
            >>> if next_check:
            ...     print(f"Win check scheduled for {next_check}")
        """
        # Get the next expiring entered giveaway
        next_giveaway = await self.giveaway_repo.get_next_expiring_entered()

        if not next_giveaway or not next_giveaway.end_time:
            # No pending giveaways, remove job if exists
            self._remove_win_check_job()
            return None

        # Schedule job for slightly after the giveaway ends
        # (add 5 minutes buffer for SteamGifts to process winner)
        run_date = next_giveaway.end_time + timedelta(minutes=5)

        # Don't schedule in the past
        if run_date <= datetime.utcnow():
            run_date = datetime.utcnow() + timedelta(minutes=1)

        # Schedule the job
        self._schedule_win_check_job(run_date)

        return run_date

    def _schedule_win_check_job(self, run_date: datetime) -> None:
        """
        Schedule or update the win check job.

        Args:
            run_date: When to run the win check
        """
        import structlog
        logger = structlog.get_logger()

        # Create the job (replace_existing=True handles updates)
        scheduler_manager.add_date_job(
            func=self._win_check_callback,
            job_id=WIN_CHECK_JOB_ID,
            run_date=run_date,
        )

        logger.info(
            "win_check_scheduled",
            run_date=run_date.isoformat(),
        )

    def _remove_win_check_job(self) -> None:
        """Remove the win check job if it exists."""
        scheduler_manager.remove_job(WIN_CHECK_JOB_ID)

    async def _win_check_callback(self) -> None:
        """
        Callback for win check job.

        Syncs wins from SteamGifts and schedules the next check.
        """
        import structlog
        logger = structlog.get_logger()

        try:
            # Sync wins
            new_wins = await self.giveaway_service.sync_wins(pages=1)

            if new_wins > 0:
                logger.info("wins_detected", new_wins=new_wins)

            # Schedule next win check
            await self.schedule_next_win_check()

        except Exception as e:
            logger.error("win_check_failed", error=str(e))
            # Still try to schedule next check
            await self.schedule_next_win_check()

    async def update_win_check_for_new_entry(
        self, giveaway_end_time: Optional[datetime]
    ) -> None:
        """
        Update win check job after entering a new giveaway.

        If the new giveaway expires sooner than the currently scheduled
        win check, update the job.

        Args:
            giveaway_end_time: End time of the newly entered giveaway

        Example:
            >>> await service.update_win_check_for_new_entry(giveaway.end_time)
        """
        if not giveaway_end_time:
            return

        # Get current job
        job = scheduler_manager.get_job(WIN_CHECK_JOB_ID)

        # Calculate when we'd check for this giveaway
        new_check_time = giveaway_end_time + timedelta(minutes=5)

        if job is None:
            # No job exists, schedule one
            self._schedule_win_check_job(new_check_time)
        elif job.next_run_time:
            # Compare naive datetimes (APScheduler returns timezone-aware)
            job_next_run_naive = job.next_run_time.replace(tzinfo=None)
            if new_check_time < job_next_run_naive:
                # New giveaway expires sooner, update the job
                self._schedule_win_check_job(new_check_time)

    def get_win_check_status(self) -> Dict[str, Any]:
        """
        Get status of the win check job.

        Returns:
            Dictionary with win check job status:
                - scheduled: Whether a win check is scheduled
                - next_check_at: When the next check is scheduled

        Example:
            >>> status = service.get_win_check_status()
            >>> if status['scheduled']:
            ...     print(f"Next check: {status['next_check_at']}")
        """
        job = scheduler_manager.get_job(WIN_CHECK_JOB_ID)

        if job and job.next_run_time:
            return {
                "scheduled": True,
                "next_check_at": job.next_run_time.isoformat(),
            }

        return {
            "scheduled": False,
            "next_check_at": None,
        }
