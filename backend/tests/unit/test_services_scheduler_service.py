"""Unit tests for SchedulerService."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from models.base import Base
from services.scheduler_service import SchedulerService
from services.giveaway_service import GiveawayService
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
async def test_run_automation_cycle_success(test_db, mock_giveaway_service):
    """Test running automation cycle successfully."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

        # Mock giveaway service methods
        # sync_giveaways is called twice: once for wishlist, once for regular
        mock_giveaway_service.sync_giveaways = AsyncMock(
            side_effect=[(2, 1), (5, 2)]  # wishlist returns (2, 1), regular returns (5, 2)
        )
        mock_giveaway_service.get_eligible_giveaways = AsyncMock(return_value=[])

        # Set up settings
        settings = await service.settings_repo.get_settings()
        settings.max_scan_pages = 3
        settings.autojoin_min_price = 50
        settings.max_entries_per_cycle = 10
        await session.commit()

        # Run cycle
        stats = await service.run_automation_cycle()

        assert stats["synced"] == 10  # (2+1) + (5+2) = 10
        assert stats["eligible"] == 0
        assert stats["entered"] == 0
        assert stats["failed"] == 0
        assert stats["points_spent"] == 0

        # Verify state was updated
        state = await service._get_or_create_state()
        assert state.last_scan_at is not None
        assert state.total_scans == 1
        assert state.total_entries == 0


@pytest.mark.asyncio
async def test_run_automation_cycle_with_entries(test_db, mock_giveaway_service):
    """Test automation cycle with successful entries."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

        # Mock giveaway objects
        mock_giveaway1 = MagicMock()
        mock_giveaway1.code = "GA1"

        mock_giveaway2 = MagicMock()
        mock_giveaway2.code = "GA2"

        # Mock entry objects
        mock_entry1 = MagicMock()
        mock_entry1.points_spent = 50

        mock_entry2 = MagicMock()
        mock_entry2.points_spent = 75

        # Mock service methods
        # sync_giveaways is called twice: once for wishlist, once for regular
        mock_giveaway_service.sync_giveaways = AsyncMock(
            side_effect=[(1, 0), (1, 0)]  # wishlist returns (1, 0), regular returns (1, 0)
        )
        mock_giveaway_service.get_eligible_giveaways = AsyncMock(
            return_value=[mock_giveaway1, mock_giveaway2]
        )
        mock_giveaway_service.enter_giveaway = AsyncMock(
            side_effect=[mock_entry1, mock_entry2]
        )

        # Run cycle
        stats = await service.run_automation_cycle()

        assert stats["synced"] == 2  # (1+0) + (1+0) = 2
        assert stats["eligible"] == 2
        assert stats["entered"] == 2
        assert stats["failed"] == 0
        assert stats["points_spent"] == 125  # 50 + 75

        # Verify state
        state = await service._get_or_create_state()
        assert state.total_entries == 2


@pytest.mark.asyncio
async def test_run_automation_cycle_with_failures(test_db, mock_giveaway_service):
    """Test automation cycle with failed entries."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

        # Mock giveaways
        mock_giveaway1 = MagicMock()
        mock_giveaway1.code = "GA1"

        mock_giveaway2 = MagicMock()
        mock_giveaway2.code = "GA2"

        # Mock entry (one success, one failure)
        mock_entry = MagicMock()
        mock_entry.points_spent = 50

        mock_giveaway_service.sync_giveaways = AsyncMock(return_value=(2, 0))
        mock_giveaway_service.get_eligible_giveaways = AsyncMock(
            return_value=[mock_giveaway1, mock_giveaway2]
        )
        # First succeeds, second fails (returns None)
        mock_giveaway_service.enter_giveaway = AsyncMock(
            side_effect=[mock_entry, None]
        )

        stats = await service.run_automation_cycle()

        assert stats["entered"] == 1
        assert stats["failed"] == 1
        assert stats["points_spent"] == 50


@pytest.mark.asyncio
async def test_run_automation_cycle_error_handling(test_db, mock_giveaway_service):
    """Test automation cycle records errors."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

        # Mock to raise an error
        mock_giveaway_service.sync_giveaways = AsyncMock(
            side_effect=Exception("API Error")
        )

        # Should raise error but record it
        with pytest.raises(Exception, match="API Error"):
            await service.run_automation_cycle()

        # Error should be recorded
        state = await service._get_or_create_state()
        assert state.total_errors == 1


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
        state.last_scan_at = datetime.utcnow()
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

        next_time = datetime.utcnow() + timedelta(minutes=30)
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
        state.last_scan_at = datetime.utcnow()
        await session.commit()

        # Reset
        reset_state = await service.reset_scheduler_stats()

        assert reset_state.total_scans == 0
        assert reset_state.total_entries == 0
        assert reset_state.total_errors == 0
        assert reset_state.last_scan_at is None
        assert reset_state.next_scan_at is None


@pytest.mark.asyncio
async def test_run_multiple_cycles_increments_counters(test_db, mock_giveaway_service):
    """Test multiple cycles increment counters correctly."""
    async with test_db() as session:
        service = SchedulerService(session, mock_giveaway_service)

        # Mock for 3 cycles
        mock_giveaway_service.sync_giveaways = AsyncMock(return_value=(1, 0))
        mock_giveaway_service.get_eligible_giveaways = AsyncMock(return_value=[])

        # Run 3 cycles
        for _ in range(3):
            await service.run_automation_cycle()

        # Check counters
        state = await service._get_or_create_state()
        assert state.total_scans == 3


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
