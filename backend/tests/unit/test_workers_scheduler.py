"""
Unit tests for the SchedulerManager.

Tests scheduler lifecycle, job management, and status reporting.
"""

import asyncio

import pytest

from workers.scheduler import SchedulerManager


@pytest.fixture
async def scheduler():
    """Create a fresh scheduler instance for each test."""
    manager = SchedulerManager()
    yield manager
    # Cleanup: stop if running
    if manager.is_running:
        manager.stop(wait=False)


async def sample_async_job():
    """Sample async job for testing."""
    await asyncio.sleep(0.01)
    return "done"


@pytest.mark.asyncio
async def test_scheduler_initialization():
    """Test scheduler initializes correctly."""
    scheduler = SchedulerManager()
    assert scheduler.scheduler is not None
    assert not scheduler.is_running
    assert not scheduler.is_paused


@pytest.mark.asyncio
async def test_scheduler_start(scheduler):
    """Test scheduler starts correctly."""
    scheduler.start()
    assert scheduler.is_running
    assert not scheduler.is_paused


@pytest.mark.asyncio
async def test_scheduler_start_idempotent(scheduler):
    """Test starting an already running scheduler does nothing."""
    scheduler.start()
    scheduler.start()  # Should not raise
    assert scheduler.is_running


@pytest.mark.asyncio
async def test_scheduler_stop(scheduler):
    """Test scheduler stops correctly."""
    scheduler.start()
    scheduler.stop()
    assert not scheduler.is_running


@pytest.mark.asyncio
async def test_scheduler_stop_idempotent(scheduler):
    """Test stopping an already stopped scheduler does nothing."""
    scheduler.stop()  # Should not raise
    assert not scheduler.is_running


@pytest.mark.asyncio
async def test_scheduler_pause(scheduler):
    """Test scheduler pause."""
    scheduler.start()
    scheduler.pause()
    assert scheduler.is_running
    assert scheduler.is_paused


@pytest.mark.asyncio
async def test_scheduler_pause_not_running(scheduler):
    """Test pausing a non-running scheduler does nothing."""
    scheduler.pause()
    assert not scheduler.is_paused


@pytest.mark.asyncio
async def test_scheduler_resume(scheduler):
    """Test scheduler resume."""
    scheduler.start()
    scheduler.pause()
    scheduler.resume()
    assert scheduler.is_running
    assert not scheduler.is_paused


@pytest.mark.asyncio
async def test_scheduler_resume_not_paused(scheduler):
    """Test resuming a non-paused scheduler does nothing."""
    scheduler.start()
    scheduler.resume()  # Should not raise
    assert not scheduler.is_paused


@pytest.mark.asyncio
async def test_add_interval_job_minutes(scheduler):
    """Test adding an interval job with minutes."""
    scheduler.start()

    job = scheduler.add_interval_job(
        func=sample_async_job,
        job_id="test_job",
        minutes=5,
    )

    assert job is not None
    assert job.id == "test_job"
    assert scheduler.get_job("test_job") is not None


@pytest.mark.asyncio
async def test_add_interval_job_seconds(scheduler):
    """Test adding an interval job with seconds."""
    scheduler.start()

    job = scheduler.add_interval_job(
        func=sample_async_job,
        job_id="test_job_seconds",
        seconds=30,
    )

    assert job is not None
    assert job.id == "test_job_seconds"


@pytest.mark.asyncio
async def test_add_interval_job_hours(scheduler):
    """Test adding an interval job with hours."""
    scheduler.start()

    job = scheduler.add_interval_job(
        func=sample_async_job,
        job_id="test_job_hours",
        hours=1,
    )

    assert job is not None
    assert job.id == "test_job_hours"


@pytest.mark.asyncio
async def test_add_interval_job_replaces_existing(scheduler):
    """Test that adding a job with same ID replaces the existing one."""
    scheduler.start()

    scheduler.add_interval_job(
        func=sample_async_job,
        job_id="test_job",
        minutes=5,
    )

    # Add again with different interval
    scheduler.add_interval_job(
        func=sample_async_job,
        job_id="test_job",
        minutes=10,
    )

    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].id == "test_job"


@pytest.mark.asyncio
async def test_add_cron_job(scheduler):
    """Test adding a cron job."""
    scheduler.start()

    job = scheduler.add_cron_job(
        func=sample_async_job,
        job_id="cron_job",
        hour=3,
        minute=0,
    )

    assert job is not None
    assert job.id == "cron_job"


@pytest.mark.asyncio
async def test_add_cron_job_with_day_of_week(scheduler):
    """Test adding a cron job with day of week."""
    scheduler.start()

    job = scheduler.add_cron_job(
        func=sample_async_job,
        job_id="weekly_job",
        hour=12,
        minute=0,
        day_of_week="mon",
    )

    assert job is not None
    assert job.id == "weekly_job"


@pytest.mark.asyncio
async def test_remove_job(scheduler):
    """Test removing a job."""
    scheduler.start()

    scheduler.add_interval_job(
        func=sample_async_job,
        job_id="to_remove",
        minutes=5,
    )

    assert scheduler.get_job("to_remove") is not None

    scheduler.remove_job("to_remove")

    assert scheduler.get_job("to_remove") is None


@pytest.mark.asyncio
async def test_remove_nonexistent_job(scheduler):
    """Test removing a non-existent job doesn't raise."""
    scheduler.start()
    scheduler.remove_job("nonexistent")  # Should not raise


@pytest.mark.asyncio
async def test_get_job(scheduler):
    """Test getting a job by ID."""
    scheduler.start()

    scheduler.add_interval_job(
        func=sample_async_job,
        job_id="get_test",
        minutes=5,
    )

    job = scheduler.get_job("get_test")
    assert job is not None
    assert job.id == "get_test"


@pytest.mark.asyncio
async def test_get_job_not_found(scheduler):
    """Test getting a non-existent job returns None."""
    scheduler.start()
    job = scheduler.get_job("nonexistent")
    assert job is None


@pytest.mark.asyncio
async def test_get_jobs(scheduler):
    """Test getting all jobs."""
    scheduler.start()

    scheduler.add_interval_job(
        func=sample_async_job,
        job_id="job1",
        minutes=5,
    )
    scheduler.add_interval_job(
        func=sample_async_job,
        job_id="job2",
        minutes=10,
    )

    jobs = scheduler.get_jobs()
    assert len(jobs) == 2
    job_ids = {job.id for job in jobs}
    assert job_ids == {"job1", "job2"}


@pytest.mark.asyncio
async def test_get_jobs_empty(scheduler):
    """Test getting jobs when none exist."""
    scheduler.start()
    jobs = scheduler.get_jobs()
    assert len(jobs) == 0


@pytest.mark.asyncio
async def test_get_status_not_running(scheduler):
    """Test status when scheduler is not running."""
    status = scheduler.get_status()

    assert status["running"] is False
    assert status["paused"] is False
    assert status["job_count"] == 0
    assert status["jobs"] == []


@pytest.mark.asyncio
async def test_get_status_running(scheduler):
    """Test status when scheduler is running."""
    scheduler.start()
    status = scheduler.get_status()

    assert status["running"] is True
    assert status["paused"] is False


@pytest.mark.asyncio
async def test_get_status_paused(scheduler):
    """Test status when scheduler is paused."""
    scheduler.start()
    scheduler.pause()
    status = scheduler.get_status()

    assert status["running"] is True
    assert status["paused"] is True


@pytest.mark.asyncio
async def test_get_status_with_jobs(scheduler):
    """Test status includes job information."""
    scheduler.start()

    scheduler.add_interval_job(
        func=sample_async_job,
        job_id="status_test",
        minutes=5,
    )

    status = scheduler.get_status()

    assert status["job_count"] == 1
    assert len(status["jobs"]) == 1
    assert status["jobs"][0]["id"] == "status_test"
    assert status["jobs"][0]["next_run"] is not None
    assert "trigger" in status["jobs"][0]


@pytest.mark.asyncio
async def test_reschedule_job(scheduler):
    """Test rescheduling a job with new interval."""
    scheduler.start()

    scheduler.add_interval_job(
        func=sample_async_job,
        job_id="reschedule_test",
        minutes=5,
    )

    scheduler.reschedule_job(
        job_id="reschedule_test",
        minutes=10,
    )

    job = scheduler.get_job("reschedule_test")
    assert job is not None
    # Job should still exist with new schedule


@pytest.mark.asyncio
async def test_scheduler_lifecycle(scheduler):
    """Test full scheduler lifecycle."""
    # Start
    scheduler.start()
    assert scheduler.is_running

    # Add job
    scheduler.add_interval_job(
        func=sample_async_job,
        job_id="lifecycle_test",
        minutes=5,
    )
    assert scheduler.get_job("lifecycle_test") is not None

    # Pause
    scheduler.pause()
    assert scheduler.is_paused

    # Resume
    scheduler.resume()
    assert not scheduler.is_paused

    # Remove job
    scheduler.remove_job("lifecycle_test")
    assert scheduler.get_job("lifecycle_test") is None

    # Stop
    scheduler.stop()
    assert not scheduler.is_running
