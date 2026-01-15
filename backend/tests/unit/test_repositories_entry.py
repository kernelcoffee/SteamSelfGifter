"""Unit tests for EntryRepository."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from models.base import Base
from models.game import Game  # Import for foreign key
from models.giveaway import Giveaway  # Import for foreign key
from models.entry import Entry
from repositories.entry import EntryRepository


# Test database setup
@pytest.fixture
async def test_db():
    """Create in-memory test database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    AsyncSessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    yield AsyncSessionLocal

    await engine.dispose()


@pytest.fixture
async def sample_giveaway(test_db):
    """Create a sample giveaway for testing."""
    async with test_db() as session:
        from repositories.giveaway import GiveawayRepository

        repo = GiveawayRepository(session)
        giveaway = await repo.create(
            code="TEST123",
            game_name="Test Game",
            price=50,
            url="http://test.com",
        )
        await session.commit()
        return giveaway.id


@pytest.mark.asyncio
async def test_get_by_giveaway_found(test_db, sample_giveaway):
    """Test getting entry by giveaway ID when it exists."""
    async with test_db() as session:
        repo = EntryRepository(session)

        entry = await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="manual",
            status="success",
        )
        await session.commit()

        result = await repo.get_by_giveaway(sample_giveaway)

        assert result is not None
        assert result.giveaway_id == sample_giveaway
        assert result.points_spent == 50


@pytest.mark.asyncio
async def test_get_by_giveaway_not_found(test_db):
    """Test getting entry by giveaway ID when it doesn't exist."""
    async with test_db() as session:
        repo = EntryRepository(session)

        result = await repo.get_by_giveaway(999)

        assert result is None


@pytest.mark.asyncio
async def test_get_recent(test_db, sample_giveaway):
    """Test getting recent entries ordered by creation time."""
    async with test_db() as session:
        repo = EntryRepository(session)

        # Create entries at different times
        for i in range(5):
            await repo.create(
                giveaway_id=sample_giveaway + i,
                points_spent=50,
                entry_type="auto",
            status="success",
            )

        await session.commit()

        recent = await repo.get_recent(limit=3)

        assert len(recent) == 3
        # Should be ordered by most recent first
        for i in range(len(recent) - 1):
            assert recent[i].created_at >= recent[i + 1].created_at


@pytest.mark.asyncio
async def test_get_recent_with_offset(test_db, sample_giveaway):
    """Test getting recent entries with pagination."""
    async with test_db() as session:
        repo = EntryRepository(session)

        for i in range(10):
            await repo.create(
                giveaway_id=sample_giveaway + i,
                points_spent=50,
                entry_type="auto",
            status="success",
            )

        await session.commit()

        # Get second page (skip first 5)
        page2 = await repo.get_recent(limit=5, offset=5)

        assert len(page2) == 5


@pytest.mark.asyncio
async def test_get_by_status(test_db, sample_giveaway):
    """Test getting entries by status."""
    async with test_db() as session:
        repo = EntryRepository(session)

        # Create entries with different statuses
        await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 1,
            points_spent=30,
            entry_type="auto",
            status="failed",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 2,
            points_spent=40,
            entry_type="auto",
            status="success",
        )

        await session.commit()

        successful = await repo.get_by_status("success")
        failed = await repo.get_by_status("failed")

        assert len(successful) == 2
        assert len(failed) == 1


@pytest.mark.asyncio
async def test_get_successful(test_db, sample_giveaway):
    """Test getting successful entries."""
    async with test_db() as session:
        repo = EntryRepository(session)

        await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 1,
            points_spent=30,
            entry_type="auto",
            status="failed",
        )

        await session.commit()

        successful = await repo.get_successful()

        assert len(successful) == 1
        assert successful[0].status == "success"


@pytest.mark.asyncio
async def test_get_failed(test_db, sample_giveaway):
    """Test getting failed entries."""
    async with test_db() as session:
        repo = EntryRepository(session)

        await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 1,
            points_spent=30,
            entry_type="auto",
            status="failed",
        )

        await session.commit()

        failed = await repo.get_failed()

        assert len(failed) == 1
        assert failed[0].status == "failed"


@pytest.mark.asyncio
async def test_get_pending(test_db, sample_giveaway):
    """Test getting pending entries."""
    async with test_db() as session:
        repo = EntryRepository(session)

        await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="auto",
            status="pending",
        )

        await session.commit()

        pending = await repo.get_pending()

        assert len(pending) == 1
        assert pending[0].status == "pending"


@pytest.mark.asyncio
async def test_get_by_entry_type(test_db, sample_giveaway):
    """Test getting entries by entry type."""
    async with test_db() as session:
        repo = EntryRepository(session)

        await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="manual",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 1,
            points_spent=30,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 2,
            points_spent=40,
            entry_type="wishlist",
            status="success",
        )

        await session.commit()

        manual = await repo.get_by_entry_type("manual")
        auto = await repo.get_by_entry_type("auto")
        wishlist = await repo.get_by_entry_type("wishlist")

        assert len(manual) == 1
        assert len(auto) == 1
        assert len(wishlist) == 1


@pytest.mark.asyncio
async def test_get_in_date_range(test_db, sample_giveaway):
    """Test getting entries within date range."""
    async with test_db() as session:
        repo = EntryRepository(session)
        now = datetime.utcnow()

        # Create entry 2 days ago
        old_entry = await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="auto",
            status="success",
        )
        old_entry.created_at = now - timedelta(days=2)

        # Create entry today
        recent_entry = await repo.create(
            giveaway_id=sample_giveaway + 1,
            points_spent=30,
            entry_type="auto",
            status="success",
        )

        await session.commit()

        # Get entries from last 24 hours
        start = now - timedelta(days=1)
        end = now + timedelta(hours=1)

        in_range = await repo.get_in_date_range(start, end)

        assert len(in_range) == 1
        assert in_range[0].giveaway_id == sample_giveaway + 1


@pytest.mark.asyncio
async def test_count_by_status(test_db, sample_giveaway):
    """Test counting entries by status."""
    async with test_db() as session:
        repo = EntryRepository(session)

        await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 1,
            points_spent=30,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 2,
            points_spent=40,
            entry_type="auto",
            status="failed",
        )

        await session.commit()

        success_count = await repo.count_by_status("success")
        failed_count = await repo.count_by_status("failed")

        assert success_count == 2
        assert failed_count == 1


@pytest.mark.asyncio
async def test_count_successful(test_db, sample_giveaway):
    """Test counting successful entries."""
    async with test_db() as session:
        repo = EntryRepository(session)

        await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 1,
            points_spent=30,
            entry_type="auto",
            status="failed",
        )

        await session.commit()

        count = await repo.count_successful()

        assert count == 1


@pytest.mark.asyncio
async def test_count_failed(test_db, sample_giveaway):
    """Test counting failed entries."""
    async with test_db() as session:
        repo = EntryRepository(session)

        await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="auto",
            status="failed",
        )

        await session.commit()

        count = await repo.count_failed()

        assert count == 1


@pytest.mark.asyncio
async def test_count_by_type(test_db, sample_giveaway):
    """Test counting entries by type."""
    async with test_db() as session:
        repo = EntryRepository(session)

        await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="manual",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 1,
            points_spent=30,
            entry_type="manual",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 2,
            points_spent=40,
            entry_type="auto",
            status="success",
        )

        await session.commit()

        manual_count = await repo.count_by_type("manual")
        auto_count = await repo.count_by_type("auto")

        assert manual_count == 2
        assert auto_count == 1


@pytest.mark.asyncio
async def test_get_total_points_spent(test_db, sample_giveaway):
    """Test calculating total points spent."""
    async with test_db() as session:
        repo = EntryRepository(session)

        await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 1,
            points_spent=30,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 2,
            points_spent=20,
            entry_type="auto",
            status="success",
        )

        await session.commit()

        total = await repo.get_total_points_spent()

        assert total == 100


@pytest.mark.asyncio
async def test_get_total_points_spent_empty(test_db):
    """Test total points when no entries exist."""
    async with test_db() as session:
        repo = EntryRepository(session)

        total = await repo.get_total_points_spent()

        assert total == 0


@pytest.mark.asyncio
async def test_get_total_points_by_status(test_db, sample_giveaway):
    """Test calculating points by status."""
    async with test_db() as session:
        repo = EntryRepository(session)

        await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 1,
            points_spent=30,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 2,
            points_spent=20,
            entry_type="auto",
            status="failed",
        )

        await session.commit()

        success_points = await repo.get_total_points_by_status("success")
        failed_points = await repo.get_total_points_by_status("failed")

        assert success_points == 80
        assert failed_points == 20


@pytest.mark.asyncio
async def test_get_success_rate(test_db, sample_giveaway):
    """Test calculating success rate."""
    async with test_db() as session:
        repo = EntryRepository(session)

        # 3 successful, 1 failed = 75% success rate
        await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 1,
            points_spent=30,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 2,
            points_spent=40,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 3,
            points_spent=20,
            entry_type="auto",
            status="failed",
        )

        await session.commit()

        rate = await repo.get_success_rate()

        assert rate == 75.0


@pytest.mark.asyncio
async def test_get_success_rate_no_entries(test_db):
    """Test success rate when no entries exist."""
    async with test_db() as session:
        repo = EntryRepository(session)

        rate = await repo.get_success_rate()

        assert rate == 0.0


@pytest.mark.asyncio
async def test_get_stats(test_db, sample_giveaway):
    """Test getting comprehensive statistics."""
    async with test_db() as session:
        repo = EntryRepository(session)

        await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="manual",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 1,
            points_spent=30,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 2,
            points_spent=20,
            entry_type="wishlist",
            status="failed",
        )

        await session.commit()

        stats = await repo.get_stats()

        assert stats["total"] == 3
        assert stats["successful"] == 2
        assert stats["failed"] == 1
        assert stats["pending"] == 0
        assert abs(stats["success_rate"] - 66.67) < 0.1  # ~66.67%
        assert stats["total_points_spent"] == 100
        assert stats["points_on_success"] == 80
        assert stats["points_on_failures"] == 20
        assert stats["by_type"]["manual"] == 1
        assert stats["by_type"]["auto"] == 1
        assert stats["by_type"]["wishlist"] == 1


@pytest.mark.asyncio
async def test_get_stats_empty(test_db):
    """Test stats when no entries exist."""
    async with test_db() as session:
        repo = EntryRepository(session)

        stats = await repo.get_stats()

        assert stats["total"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["total_points_spent"] == 0


@pytest.mark.asyncio
async def test_get_recent_failures(test_db, sample_giveaway):
    """Test getting recent failed entries."""
    async with test_db() as session:
        repo = EntryRepository(session)

        await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="auto",
            status="failed",
            error_message="Insufficient points",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 1,
            points_spent=30,
            entry_type="auto",
            status="success",
        )

        await session.commit()

        failures = await repo.get_recent_failures(limit=10)

        assert len(failures) == 1
        assert failures[0].status == "failed"
        assert failures[0].error_message == "Insufficient points"


@pytest.mark.asyncio
async def test_get_entries_since(test_db, sample_giveaway):
    """Test getting entries since a specific time."""
    async with test_db() as session:
        repo = EntryRepository(session)
        now = datetime.utcnow()

        # Create old entry
        old_entry = await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="auto",
            status="success",
        )
        old_entry.created_at = now - timedelta(hours=2)

        # Create recent entry
        await repo.create(
            giveaway_id=sample_giveaway + 1,
            points_spent=30,
            entry_type="auto",
            status="success",
        )

        await session.commit()

        # Get entries from last hour
        one_hour_ago = now - timedelta(hours=1)
        recent = await repo.get_entries_since(one_hour_ago)

        assert len(recent) == 1
        assert recent[0].giveaway_id == sample_giveaway + 1


@pytest.mark.asyncio
async def test_has_entry_for_giveaway_true(test_db, sample_giveaway):
    """Test checking if entry exists for giveaway (exists)."""
    async with test_db() as session:
        repo = EntryRepository(session)

        await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="auto",
            status="success",
        )
        await session.commit()

        has_entry = await repo.has_entry_for_giveaway(sample_giveaway)

        assert has_entry is True


@pytest.mark.asyncio
async def test_has_entry_for_giveaway_false(test_db, sample_giveaway):
    """Test checking if entry exists for giveaway (doesn't exist)."""
    async with test_db() as session:
        repo = EntryRepository(session)

        has_entry = await repo.has_entry_for_giveaway(sample_giveaway)

        assert has_entry is False


@pytest.mark.asyncio
async def test_get_average_points_per_entry(test_db, sample_giveaway):
    """Test calculating average points per entry."""
    async with test_db() as session:
        repo = EntryRepository(session)

        await repo.create(
            giveaway_id=sample_giveaway,
            points_spent=50,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 1,
            points_spent=30,
            entry_type="auto",
            status="success",
        )
        await repo.create(
            giveaway_id=sample_giveaway + 2,
            points_spent=40,
            entry_type="auto",
            status="success",
        )

        await session.commit()

        avg = await repo.get_average_points_per_entry()

        assert avg == 40.0  # (50 + 30 + 40) / 3 = 40


@pytest.mark.asyncio
async def test_get_average_points_per_entry_no_entries(test_db):
    """Test average points when no entries exist."""
    async with test_db() as session:
        repo = EntryRepository(session)

        avg = await repo.get_average_points_per_entry()

        assert avg == 0.0
