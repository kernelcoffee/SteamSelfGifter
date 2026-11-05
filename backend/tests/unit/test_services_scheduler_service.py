"""Unit tests for SchedulerService."""

import inspect
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.time import utcnow
from models.base import Base
from models.giveaway import Giveaway
from services.scheduler_service import WIN_CHECK_JOB_ID, SchedulerService
from workers.scheduler import SchedulerManager
from workers.win_check import run_win_check


# Test database setup
@pytest.fixture
async def test_db():
    """Create in-memory test database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    yield async_session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def fresh_scheduler_manager():
    """Create a fresh SchedulerManager and patch it into the service module."""
    fresh_manager = SchedulerManager()
    with patch("services.scheduler_service.scheduler_manager", fresh_manager):
        yield fresh_manager
        # Stop if still running
        if fresh_manager.is_running:
            fresh_manager.stop(wait=False)


@pytest.mark.asyncio
async def test_scheduler_service_init(test_db):
    """Test SchedulerService initialization."""
    async with test_db() as session:
        service = SchedulerService(session)

        assert service.session == session
        assert not hasattr(service, "giveaway_service")
        assert service.settings_repo is not None


@pytest.mark.asyncio
async def test_get_or_create_state_creates(test_db):
    """Test _get_or_create_state creates state if not exists."""
    async with test_db() as session:
        service = SchedulerService(session)

        state = await service._get_or_create_state()

        assert state is not None
        assert state.id == 1
        assert state.total_scans == 0
        assert state.total_entries == 0


@pytest.mark.asyncio
async def test_get_or_create_state_reuses_existing(test_db):
    """Test _get_or_create_state returns existing state."""
    async with test_db() as session:
        service = SchedulerService(session)

        # Create first
        state1 = await service._get_or_create_state()
        state1.total_scans = 10
        await session.commit()

        # Get again
        state2 = await service._get_or_create_state()

        assert state2.id == state1.id
        assert state2.total_scans == 10


@pytest.mark.asyncio
async def test_get_scheduler_stats(test_db):
    """Test getting scheduler statistics."""
    async with test_db() as session:
        service = SchedulerService(session)

        # Create state with some data
        state = await service._get_or_create_state()
        state.total_scans = 10
        state.total_entries = 25
        state.total_errors = 2
        state.last_scan_at = utcnow()
        await session.commit()

        stats = await service.get_scheduler_stats()

        assert stats["total_scans"] == 10
        assert stats["total_entries"] == 25
        assert stats["total_errors"] == 2
        assert stats["has_run"] is True
        assert stats["last_scan_at"] is not None


@pytest.mark.asyncio
async def test_update_next_scan_time(test_db):
    """Test updating next scan time."""
    async with test_db() as session:
        service = SchedulerService(session)

        next_time = utcnow() + timedelta(minutes=30)
        state = await service.update_next_scan_time(next_time)

        assert state.next_scan_at is not None
        assert abs((state.next_scan_at - next_time).total_seconds()) < 1


@pytest.mark.asyncio
async def test_reset_scheduler_stats(test_db):
    """Test resetting scheduler statistics."""
    async with test_db() as session:
        service = SchedulerService(session)

        # Create state with data
        state = await service._get_or_create_state()
        state.total_scans = 100
        state.total_entries = 250
        state.total_errors = 5
        state.last_scan_at = utcnow()
        await session.commit()

        # Reset
        reset_state = await service.reset_scheduler_stats()

        assert reset_state.total_scans == 0
        assert reset_state.total_entries == 0
        assert reset_state.total_errors == 0
        assert reset_state.last_scan_at is None
        assert reset_state.next_scan_at is None


@pytest.mark.asyncio
async def test_start_automation(test_db, fresh_scheduler_manager):
    """Test starting automation."""
    async with test_db() as session:
        service = SchedulerService(session)

        service.start_automation()

        assert service.is_automation_running() is True
        service.stop_automation(wait=False)


@pytest.mark.asyncio
async def test_stop_automation(test_db, fresh_scheduler_manager):
    """Test stopping automation."""
    async with test_db() as session:
        service = SchedulerService(session)

        service.start_automation()
        service.stop_automation(wait=False)

        assert service.is_automation_running() is False


@pytest.mark.asyncio
async def test_pause_automation(test_db, fresh_scheduler_manager):
    """Test pausing automation."""
    async with test_db() as session:
        service = SchedulerService(session)

        service.start_automation()
        service.pause_automation()

        # Paused means running but not active
        status = service.get_scheduler_status()
        assert status["running"] is True
        assert status["paused"] is True
        assert service.is_automation_running() is False

        service.stop_automation(wait=False)


@pytest.mark.asyncio
async def test_resume_automation(test_db, fresh_scheduler_manager):
    """Test resuming automation."""
    async with test_db() as session:
        service = SchedulerService(session)

        service.start_automation()
        service.pause_automation()
        service.resume_automation()

        status = service.get_scheduler_status()
        assert status["paused"] is False
        assert service.is_automation_running() is True

        service.stop_automation(wait=False)


@pytest.mark.asyncio
async def test_get_scheduler_status(test_db, fresh_scheduler_manager):
    """Test getting scheduler status."""
    async with test_db() as session:
        service = SchedulerService(session)

        service.start_automation()

        status = service.get_scheduler_status()

        assert "running" in status
        assert "paused" in status
        assert "job_count" in status
        assert "jobs" in status
        assert status["running"] is True
        assert status["paused"] is False

        service.stop_automation(wait=False)


@pytest.mark.asyncio
async def test_is_automation_running_not_started(test_db, fresh_scheduler_manager):
    """Test is_automation_running when not started."""
    async with test_db() as session:
        service = SchedulerService(session)

        # Initially not running
        assert service.is_automation_running() is False


def _win_check_run_time(manager: SchedulerManager) -> datetime | None:
    """Naive UTC run time of the registered win_check job, or None."""
    job = manager.get_job(WIN_CHECK_JOB_ID)
    if job is None or job.next_run_time is None:
        return None
    return job.next_run_time.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_schedule_win_check_job_registers_module_function(test_db: async_sessionmaker[AsyncSession]) -> None:
    """The win_check job is the module-level worker coroutine, never a method
    bound to this (possibly request-scoped) service."""
    manager = MagicMock()
    run_date = utcnow() + timedelta(days=1)

    with patch("services.scheduler_service.scheduler_manager", manager):
        async with test_db() as session:
            SchedulerService(session)._schedule_win_check_job(run_date)

    manager.add_date_job.assert_called_once()
    kwargs = manager.add_date_job.call_args.kwargs
    assert kwargs["func"] is run_win_check
    assert not inspect.ismethod(kwargs["func"])
    assert kwargs["job_id"] == "win_check"
    assert kwargs["run_date"] == run_date


@pytest.mark.asyncio
async def test_registered_win_check_job_holds_no_service(
    test_db: async_sessionmaker[AsyncSession],
    fresh_scheduler_manager: SchedulerManager,
) -> None:
    """The job stored in APScheduler references neither the service nor its
    session, so it survives the request that scheduled it."""
    fresh_scheduler_manager.start()
    async with test_db() as session:
        service = SchedulerService(session)
        await service.update_win_check_for_new_entry(utcnow() + timedelta(days=1))

    job = fresh_scheduler_manager.get_job(WIN_CHECK_JOB_ID)
    assert job is not None
    assert job.func is run_win_check
    assert job.args == ()
    assert job.kwargs == {}


@pytest.mark.asyncio
async def test_update_win_check_for_new_entry_schedules_when_no_job(
    test_db: async_sessionmaker[AsyncSession],
    fresh_scheduler_manager: SchedulerManager,
) -> None:
    """With no job yet, a new entry schedules one 5 minutes after it ends."""
    fresh_scheduler_manager.start()
    end_time = utcnow() + timedelta(days=1)

    async with test_db() as session:
        await SchedulerService(session).update_win_check_for_new_entry(end_time)

    assert _win_check_run_time(fresh_scheduler_manager) == end_time + timedelta(minutes=5)


@pytest.mark.asyncio
async def test_update_win_check_for_new_entry_keeps_sooner_job(
    test_db: async_sessionmaker[AsyncSession],
    fresh_scheduler_manager: SchedulerManager,
) -> None:
    """An existing job sooner than the new entry's check time is left unchanged."""
    fresh_scheduler_manager.start()
    soon = utcnow() + timedelta(hours=2)

    async with test_db() as session:
        service = SchedulerService(session)
        await service.update_win_check_for_new_entry(soon)
        await service.update_win_check_for_new_entry(soon + timedelta(days=2))

    assert _win_check_run_time(fresh_scheduler_manager) == soon + timedelta(minutes=5)


@pytest.mark.asyncio
async def test_update_win_check_for_new_entry_moves_job_earlier(
    test_db: async_sessionmaker[AsyncSession],
    fresh_scheduler_manager: SchedulerManager,
) -> None:
    """A new entry ending sooner than the scheduled check moves the job earlier."""
    fresh_scheduler_manager.start()
    later = utcnow() + timedelta(days=2)
    sooner = utcnow() + timedelta(hours=2)

    async with test_db() as session:
        service = SchedulerService(session)
        await service.update_win_check_for_new_entry(later)
        await service.update_win_check_for_new_entry(sooner)

    assert _win_check_run_time(fresh_scheduler_manager) == sooner + timedelta(minutes=5)


@pytest.mark.asyncio
async def test_update_win_check_for_new_entry_ignores_missing_end_time(
    test_db: async_sessionmaker[AsyncSession],
    fresh_scheduler_manager: SchedulerManager,
) -> None:
    """A giveaway without an end time schedules nothing."""
    fresh_scheduler_manager.start()

    async with test_db() as session:
        await SchedulerService(session).update_win_check_for_new_entry(None)

    assert fresh_scheduler_manager.get_job(WIN_CHECK_JOB_ID) is None


@pytest.mark.asyncio
async def test_schedule_next_win_check_targets_soonest_entered_giveaway(
    test_db: async_sessionmaker[AsyncSession],
    fresh_scheduler_manager: SchedulerManager,
) -> None:
    """The job runs 5 minutes after the soonest-ending entered, not-won giveaway."""
    fresh_scheduler_manager.start()
    soonest = utcnow() + timedelta(hours=3)

    async with test_db() as session:
        session.add_all([
            Giveaway(code="SOON1", url="/giveaway/SOON1/", game_name="Soon", price=10,
                     end_time=soonest, is_entered=True),
            Giveaway(code="LATE1", url="/giveaway/LATE1/", game_name="Late", price=10,
                     end_time=soonest + timedelta(days=1), is_entered=True),
            Giveaway(code="NOTIN", url="/giveaway/NOTIN/", game_name="Not entered", price=10,
                     end_time=soonest - timedelta(hours=1), is_entered=False),
        ])
        await session.commit()

        run_date = await SchedulerService(session).schedule_next_win_check()

    assert run_date == soonest + timedelta(minutes=5)
    assert _win_check_run_time(fresh_scheduler_manager) == run_date


@pytest.mark.asyncio
async def test_schedule_next_win_check_removes_job_when_nothing_pending(
    test_db: async_sessionmaker[AsyncSession],
    fresh_scheduler_manager: SchedulerManager,
) -> None:
    """With no entered giveaway pending, the existing job is removed."""
    fresh_scheduler_manager.start()

    async with test_db() as session:
        service = SchedulerService(session)
        await service.update_win_check_for_new_entry(utcnow() + timedelta(days=1))

        assert await service.schedule_next_win_check() is None

    assert fresh_scheduler_manager.get_job(WIN_CHECK_JOB_ID) is None
