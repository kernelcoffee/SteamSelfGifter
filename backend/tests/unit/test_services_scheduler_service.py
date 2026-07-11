"""Unit tests for SchedulerService."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.time import utcnow
from models.base import Base
from services.giveaway_service import GiveawayService
from services.scheduler_service import SchedulerService
from workers.scheduler import SchedulerManager


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
def mock_giveaway_service():
    """Create mock GiveawayService."""
    service = MagicMock(spec=GiveawayService)
    return service


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
async def test_scheduler_service_init(test_db, mock_giveaway_service):
    """Test SchedulerService initialization."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

        assert service.session == session
        assert service.giveaway_service == mock_giveaway_service
        assert service.settings_repo is not None


@pytest.mark.asyncio
async def test_get_or_create_state_creates(test_db, mock_giveaway_service):
    """Test _get_or_create_state creates state if not exists."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

        state = await service._get_or_create_state()

        assert state is not None
        assert state.id == 1
        assert state.total_scans == 0
        assert state.total_entries == 0


@pytest.mark.asyncio
async def test_get_or_create_state_reuses_existing(test_db, mock_giveaway_service):
    """Test _get_or_create_state returns existing state."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

        # Create first
        state1 = await service._get_or_create_state()
        state1.total_scans = 10
        await session.commit()

        # Get again
        state2 = await service._get_or_create_state()

        assert state2.id == state1.id
        assert state2.total_scans == 10


@pytest.mark.asyncio
async def test_get_scheduler_stats(test_db, mock_giveaway_service):
    """Test getting scheduler statistics."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

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
async def test_update_next_scan_time(test_db, mock_giveaway_service):
    """Test updating next scan time."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

        next_time = utcnow() + timedelta(minutes=30)
        state = await service.update_next_scan_time(next_time)

        assert state.next_scan_at is not None
        assert abs((state.next_scan_at - next_time).total_seconds()) < 1


@pytest.mark.asyncio
async def test_reset_scheduler_stats(test_db, mock_giveaway_service):
    """Test resetting scheduler statistics."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

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
async def test_start_automation(test_db, mock_giveaway_service, fresh_scheduler_manager):
    """Test starting automation."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

        service.start_automation()

        assert service.is_automation_running() is True
        service.stop_automation(wait=False)


@pytest.mark.asyncio
async def test_stop_automation(test_db, mock_giveaway_service, fresh_scheduler_manager):
    """Test stopping automation."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

        service.start_automation()
        service.stop_automation(wait=False)

        assert service.is_automation_running() is False


@pytest.mark.asyncio
async def test_pause_automation(test_db, mock_giveaway_service, fresh_scheduler_manager):
    """Test pausing automation."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

        service.start_automation()
        service.pause_automation()

        # Paused means running but not active
        status = service.get_scheduler_status()
        assert status["running"] is True
        assert status["paused"] is True
        assert service.is_automation_running() is False

        service.stop_automation(wait=False)


@pytest.mark.asyncio
async def test_resume_automation(test_db, mock_giveaway_service, fresh_scheduler_manager):
    """Test resuming automation."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

        service.start_automation()
        service.pause_automation()
        service.resume_automation()

        status = service.get_scheduler_status()
        assert status["paused"] is False
        assert service.is_automation_running() is True

        service.stop_automation(wait=False)


@pytest.mark.asyncio
async def test_get_scheduler_status(test_db, mock_giveaway_service, fresh_scheduler_manager):
    """Test getting scheduler status."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

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
async def test_is_automation_running_not_started(test_db, mock_giveaway_service, fresh_scheduler_manager):
    """Test is_automation_running when not started."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

        # Initially not running
        assert service.is_automation_running() is False
