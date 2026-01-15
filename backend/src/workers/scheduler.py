"""
Scheduler manager for background job scheduling.

Uses APScheduler to manage periodic tasks like giveaway scanning
and entry processing.
"""

from typing import Callable, Any
from datetime import datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.job import Job

from core.config import settings

logger = structlog.get_logger()


class SchedulerManager:
    """
    Manages background job scheduling using APScheduler.

    Provides methods to:
    - Start/stop the scheduler
    - Add/remove jobs
    - Get scheduler status
    - Pause/resume jobs

    Design Notes:
        - Uses AsyncIOScheduler for async job execution
        - Memory-based job store (jobs don't persist across restarts)
        - Single instance pattern via module-level scheduler_manager
        - All job functions must be async

    Usage:
        >>> from workers.scheduler import scheduler_manager
        >>> scheduler_manager.start()
        >>> scheduler_manager.add_interval_job(
        ...     func=my_async_func,
        ...     job_id="my_job",
        ...     minutes=30
        ... )
    """

    def __init__(self) -> None:
        """Initialize the scheduler manager."""
        # Use memory job store (simpler, no persistence needed for this app)
        jobstores = {"default": MemoryJobStore()}

        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone=settings.scheduler_timezone,
        )
        self._is_running = False
        self._is_paused = False

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._is_running

    @property
    def is_paused(self) -> bool:
        """Check if scheduler is paused."""
        return self._is_paused

    def start(self) -> None:
        """
        Start the scheduler.

        If already running, does nothing.
        """
        if not self._is_running:
            self.scheduler.start()
            self._is_running = True
            self._is_paused = False
            logger.info("scheduler_started")

    def stop(self, wait: bool = True) -> None:
        """
        Stop the scheduler.

        Args:
            wait: If True, wait for running jobs to complete
        """
        if self._is_running:
            self.scheduler.shutdown(wait=wait)
            self._is_running = False
            self._is_paused = False
            logger.info("scheduler_stopped")

    def pause(self) -> None:
        """
        Pause all jobs.

        Jobs remain scheduled but won't execute until resumed.
        """
        if self.scheduler.running and not self._is_paused:
            self.scheduler.pause()
            self._is_paused = True
            logger.info("scheduler_paused")

    def resume(self) -> None:
        """
        Resume all paused jobs.
        """
        if self.scheduler.running and self._is_paused:
            self.scheduler.resume()
            self._is_paused = False
            logger.info("scheduler_resumed")

    def add_interval_job(
        self,
        func: Callable[..., Any],
        job_id: str,
        minutes: int | None = None,
        seconds: int | None = None,
        hours: int | None = None,
        **kwargs: Any,
    ) -> Job:
        """
        Add a job that runs at fixed intervals.

        Args:
            func: Async function to execute
            job_id: Unique job identifier
            minutes: Interval in minutes
            seconds: Interval in seconds
            hours: Interval in hours
            **kwargs: Additional arguments passed to the job function

        Returns:
            The created Job instance

        Example:
            >>> scheduler_manager.add_interval_job(
            ...     func=scan_giveaways,
            ...     job_id="giveaway_scanner",
            ...     minutes=30
            ... )
        """
        # Only pass non-None values to IntervalTrigger
        trigger_kwargs = {}
        if minutes is not None:
            trigger_kwargs["minutes"] = minutes
        if seconds is not None:
            trigger_kwargs["seconds"] = seconds
        if hours is not None:
            trigger_kwargs["hours"] = hours

        trigger = IntervalTrigger(**trigger_kwargs)

        job = self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            **kwargs,
        )

        logger.info(
            "job_added",
            job_id=job_id,
            trigger_type="interval",
            interval_minutes=minutes,
            interval_seconds=seconds,
            interval_hours=hours,
        )

        return job

    def add_cron_job(
        self,
        func: Callable[..., Any],
        job_id: str,
        hour: int | str | None = None,
        minute: int | str | None = None,
        second: int | str | None = None,
        day_of_week: str | None = None,
        **kwargs: Any,
    ) -> Job:
        """
        Add a job that runs on a cron schedule.

        Args:
            func: Async function to execute
            job_id: Unique job identifier
            hour: Hour (0-23) or cron expression
            minute: Minute (0-59) or cron expression
            second: Second (0-59) or cron expression
            day_of_week: Day of week (mon-sun) or cron expression
            **kwargs: Additional arguments passed to the job function

        Returns:
            The created Job instance

        Example:
            >>> scheduler_manager.add_cron_job(
            ...     func=daily_cleanup,
            ...     job_id="daily_cleanup",
            ...     hour=3,
            ...     minute=0
            ... )
        """
        trigger = CronTrigger(
            hour=hour,
            minute=minute,
            second=second,
            day_of_week=day_of_week,
        )

        job = self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            **kwargs,
        )

        logger.info(
            "job_added",
            job_id=job_id,
            trigger_type="cron",
            hour=hour,
            minute=minute,
        )

        return job

    def add_date_job(
        self,
        func: Callable[..., Any],
        job_id: str,
        run_date: datetime,
        **kwargs: Any,
    ) -> Job:
        """
        Add a job that runs once at a specific date/time.

        Args:
            func: Async function to execute
            job_id: Unique job identifier
            run_date: When to run the job (datetime)
            **kwargs: Additional arguments passed to the job function

        Returns:
            The created Job instance

        Example:
            >>> from datetime import datetime, timedelta
            >>> run_at = datetime.utcnow() + timedelta(hours=2)
            >>> scheduler_manager.add_date_job(
            ...     func=check_wins,
            ...     job_id="win_check_123",
            ...     run_date=run_at
            ... )
        """
        trigger = DateTrigger(run_date=run_date)

        job = self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            **kwargs,
        )

        logger.info(
            "job_added",
            job_id=job_id,
            trigger_type="date",
            run_date=run_date.isoformat(),
        )

        return job

    def remove_job(self, job_id: str) -> None:
        """
        Remove a job by ID.

        Args:
            job_id: The job identifier to remove
        """
        try:
            self.scheduler.remove_job(job_id)
            logger.info("job_removed", job_id=job_id)
        except Exception as e:
            logger.warning("job_remove_failed", job_id=job_id, error=str(e))

    def get_job(self, job_id: str) -> Job | None:
        """
        Get a job by ID.

        Args:
            job_id: The job identifier

        Returns:
            The Job instance or None if not found
        """
        return self.scheduler.get_job(job_id)

    def get_jobs(self) -> list[Job]:
        """
        Get all scheduled jobs.

        Returns:
            List of Job instances
        """
        return self.scheduler.get_jobs()

    def get_status(self) -> dict[str, Any]:
        """
        Get scheduler status.

        Returns:
            Dictionary with scheduler state and job information
        """
        jobs = self.get_jobs()
        job_info = []

        for job in jobs:
            next_run = job.next_run_time
            job_info.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": next_run.isoformat() if next_run else None,
                    "trigger": str(job.trigger),
                }
            )

        return {
            "running": self.is_running,
            "paused": self.is_paused,
            "job_count": len(jobs),
            "jobs": job_info,
        }

    def reschedule_job(
        self,
        job_id: str,
        minutes: int | None = None,
        seconds: int | None = None,
        hours: int | None = None,
    ) -> None:
        """
        Reschedule an existing job with a new interval.

        Args:
            job_id: The job identifier
            minutes: New interval in minutes
            seconds: New interval in seconds
            hours: New interval in hours
        """
        # Only pass non-None values to IntervalTrigger
        trigger_kwargs = {}
        if minutes is not None:
            trigger_kwargs["minutes"] = minutes
        if seconds is not None:
            trigger_kwargs["seconds"] = seconds
        if hours is not None:
            trigger_kwargs["hours"] = hours

        trigger = IntervalTrigger(**trigger_kwargs)

        self.scheduler.reschedule_job(job_id, trigger=trigger)
        logger.info(
            "job_rescheduled",
            job_id=job_id,
            interval_minutes=minutes,
            interval_seconds=seconds,
            interval_hours=hours,
        )


# Global scheduler instance
scheduler_manager = SchedulerManager()
