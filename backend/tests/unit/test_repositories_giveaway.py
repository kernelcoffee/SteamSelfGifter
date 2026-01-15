"""Unit tests for GiveawayRepository."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from models.base import Base
from models.game import Game  # Import Game so foreign key works
from models.giveaway import Giveaway
from repositories.giveaway import GiveawayRepository


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


@pytest.mark.asyncio
async def test_get_by_code_found(test_db):
    """Test getting giveaway by code when it exists."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        # Create giveaway
        giveaway = await repo.create(
            code="ABC123", game_name="Portal 2", price=50, url="http://test.com"
        )
        await session.commit()

        # Retrieve by code
        result = await repo.get_by_code("ABC123")

        assert result is not None
        assert result.code == "ABC123"
        assert result.game_name == "Portal 2"


@pytest.mark.asyncio
async def test_get_by_code_not_found(test_db):
    """Test getting giveaway by code when it doesn't exist."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        result = await repo.get_by_code("NONEXISTENT")

        assert result is None


@pytest.mark.asyncio
async def test_get_active_returns_only_active(test_db):
    """Test getting active giveaways excludes expired ones."""
    async with test_db() as session:
        repo = GiveawayRepository(session)
        now = datetime.utcnow()

        # Active giveaway
        await repo.create(
            code="ACTIVE1",
            game_name="Game 1",
            price=50,
            url="http://test.com/1",
            end_time=now + timedelta(hours=24),
        )

        # Expired giveaway
        await repo.create(
            code="EXPIRED1",
            game_name="Game 2",
            price=30,
            url="http://test.com/2",
            end_time=now - timedelta(hours=1),
        )

        await session.commit()

        active = await repo.get_active()

        assert len(active) == 1
        assert active[0].code == "ACTIVE1"


@pytest.mark.asyncio
async def test_get_active_excludes_hidden(test_db):
    """Test getting active giveaways excludes hidden ones."""
    async with test_db() as session:
        repo = GiveawayRepository(session)
        now = datetime.utcnow()

        # Active, not hidden
        await repo.create(
            code="VISIBLE",
            game_name="Game 1",
            price=50,
            url="http://test.com/1",
            end_time=now + timedelta(hours=24),
            is_hidden=False,
        )

        # Active, but hidden
        await repo.create(
            code="HIDDEN",
            game_name="Game 2",
            price=30,
            url="http://test.com/2",
            end_time=now + timedelta(hours=24),
            is_hidden=True,
        )

        await session.commit()

        active = await repo.get_active()

        assert len(active) == 1
        assert active[0].code == "VISIBLE"


@pytest.mark.asyncio
async def test_get_active_with_limit(test_db):
    """Test getting active giveaways with limit."""
    async with test_db() as session:
        repo = GiveawayRepository(session)
        now = datetime.utcnow()

        # Create 5 active giveaways
        for i in range(5):
            await repo.create(
                code=f"GA{i}",
                game_name=f"Game {i}",
                price=50,
                url=f"http://test.com/{i}",
                end_time=now + timedelta(hours=i + 1),
            )

        await session.commit()

        active = await repo.get_active(limit=3)

        assert len(active) == 3


@pytest.mark.asyncio
async def test_get_active_ordered_by_end_time(test_db):
    """Test active giveaways are ordered by end_time (soonest first)."""
    async with test_db() as session:
        repo = GiveawayRepository(session)
        now = datetime.utcnow()

        # Create in reverse order
        await repo.create(
            code="LATER",
            game_name="Game 1",
            price=50,
            url="http://test.com/1",
            end_time=now + timedelta(hours=48),
        )
        await repo.create(
            code="SOONER",
            game_name="Game 2",
            price=30,
            url="http://test.com/2",
            end_time=now + timedelta(hours=12),
        )

        await session.commit()

        active = await repo.get_active()

        assert len(active) == 2
        assert active[0].code == "SOONER"  # Ends first
        assert active[1].code == "LATER"


@pytest.mark.asyncio
async def test_get_eligible_basic_filters(test_db):
    """Test getting eligible giveaways with basic price filter."""
    async with test_db() as session:
        repo = GiveawayRepository(session)
        now = datetime.utcnow()

        # Eligible (price >= 50)
        await repo.create(
            code="ELIGIBLE",
            game_name="Game 1",
            price=100,
            url="http://test.com/1",
            end_time=now + timedelta(hours=24),
        )

        # Too cheap
        await repo.create(
            code="CHEAP",
            game_name="Game 2",
            price=10,
            url="http://test.com/2",
            end_time=now + timedelta(hours=24),
        )

        await session.commit()

        eligible = await repo.get_eligible(min_price=50)

        assert len(eligible) == 1
        assert eligible[0].code == "ELIGIBLE"


@pytest.mark.asyncio
async def test_get_eligible_excludes_entered(test_db):
    """Test eligible giveaways excludes already entered."""
    async with test_db() as session:
        repo = GiveawayRepository(session)
        now = datetime.utcnow()

        # Not entered
        await repo.create(
            code="AVAILABLE",
            game_name="Game 1",
            price=50,
            url="http://test.com/1",
            end_time=now + timedelta(hours=24),
            is_entered=False,
        )

        # Already entered
        await repo.create(
            code="ENTERED",
            game_name="Game 2",
            price=50,
            url="http://test.com/2",
            end_time=now + timedelta(hours=24),
            is_entered=True,
        )

        await session.commit()

        eligible = await repo.get_eligible(min_price=10)

        assert len(eligible) == 1
        assert eligible[0].code == "AVAILABLE"


@pytest.mark.asyncio
async def test_get_eligible_with_max_price(test_db):
    """Test eligible giveaways with max price filter."""
    async with test_db() as session:
        repo = GiveawayRepository(session)
        now = datetime.utcnow()

        await repo.create(
            code="GA1",
            game_name="Game 1",
            price=50,
            url="http://test.com/1",
            end_time=now + timedelta(hours=24),
        )
        await repo.create(
            code="GA2",
            game_name="Game 2",
            price=150,
            url="http://test.com/2",
            end_time=now + timedelta(hours=24),
        )

        await session.commit()

        # Min 10, max 100
        eligible = await repo.get_eligible(min_price=10, max_price=100)

        assert len(eligible) == 1
        assert eligible[0].code == "GA1"


@pytest.mark.asyncio
async def test_get_eligible_ordered_by_price_desc(test_db):
    """Test eligible giveaways ordered by price descending."""
    async with test_db() as session:
        repo = GiveawayRepository(session)
        now = datetime.utcnow()

        await repo.create(
            code="LOW",
            game_name="Game 1",
            price=30,
            url="http://test.com/1",
            end_time=now + timedelta(hours=24),
        )
        await repo.create(
            code="HIGH",
            game_name="Game 2",
            price=100,
            url="http://test.com/2",
            end_time=now + timedelta(hours=24),
        )

        await session.commit()

        eligible = await repo.get_eligible(min_price=10)

        assert len(eligible) == 2
        assert eligible[0].code == "HIGH"  # Highest price first
        assert eligible[1].code == "LOW"


@pytest.mark.asyncio
async def test_get_by_game(test_db):
    """Test getting giveaways by game ID."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        await repo.create(
            code="GA1",
            game_name="CS:GO",
            game_id=730,
            price=50,
            url="http://test.com/1",
        )
        await repo.create(
            code="GA2",
            game_name="CS:GO",
            game_id=730,
            price=30,
            url="http://test.com/2",
        )
        await repo.create(
            code="GA3",
            game_name="Portal 2",
            game_id=620,
            price=40,
            url="http://test.com/3",
        )

        await session.commit()

        cs_giveaways = await repo.get_by_game(730)

        assert len(cs_giveaways) == 2
        assert all(ga.game_id == 730 for ga in cs_giveaways)


@pytest.mark.asyncio
async def test_get_hidden(test_db):
    """Test getting hidden giveaways."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        await repo.create(
            code="VISIBLE",
            game_name="Game 1",
            price=50,
            url="http://test.com/1",
            is_hidden=False,
        )
        await repo.create(
            code="HIDDEN1",
            game_name="Game 2",
            price=30,
            url="http://test.com/2",
            is_hidden=True,
        )
        await repo.create(
            code="HIDDEN2",
            game_name="Game 3",
            price=40,
            url="http://test.com/3",
            is_hidden=True,
        )

        await session.commit()

        hidden = await repo.get_hidden()

        assert len(hidden) == 2
        assert all(ga.is_hidden for ga in hidden)


@pytest.mark.asyncio
async def test_get_entered(test_db):
    """Test getting entered giveaways."""
    async with test_db() as session:
        repo = GiveawayRepository(session)
        now = datetime.utcnow()

        await repo.create(
            code="NOT_ENTERED",
            game_name="Game 1",
            price=50,
            url="http://test.com/1",
            is_entered=False,
        )
        await repo.create(
            code="ENTERED1",
            game_name="Game 2",
            price=30,
            url="http://test.com/2",
            is_entered=True,
            entered_at=now - timedelta(hours=2),
        )
        await repo.create(
            code="ENTERED2",
            game_name="Game 3",
            price=40,
            url="http://test.com/3",
            is_entered=True,
            entered_at=now - timedelta(hours=1),
        )

        await session.commit()

        entered = await repo.get_entered()

        assert len(entered) == 2
        assert all(ga.is_entered for ga in entered)
        # Most recent first
        assert entered[0].code == "ENTERED2"


@pytest.mark.asyncio
async def test_get_entered_with_limit(test_db):
    """Test getting entered giveaways with limit."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        for i in range(5):
            await repo.create(
                code=f"GA{i}",
                game_name=f"Game {i}",
                price=50,
                url=f"http://test.com/{i}",
                is_entered=True,
            )

        await session.commit()

        entered = await repo.get_entered(limit=3)

        assert len(entered) == 3


@pytest.mark.asyncio
async def test_hide_giveaway(test_db):
    """Test hiding a giveaway."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        giveaway = await repo.create(
            code="GA1", game_name="Game 1", price=50, url="http://test.com"
        )
        await session.commit()

        hidden = await repo.hide_giveaway(giveaway.id)
        await session.commit()

        assert hidden is not None
        assert hidden.is_hidden is True


@pytest.mark.asyncio
async def test_hide_giveaway_nonexistent(test_db):
    """Test hiding nonexistent giveaway returns None."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        result = await repo.hide_giveaway(999)

        assert result is None


@pytest.mark.asyncio
async def test_unhide_giveaway(test_db):
    """Test unhiding a giveaway."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        giveaway = await repo.create(
            code="GA1",
            game_name="Game 1",
            price=50,
            url="http://test.com",
            is_hidden=True,
        )
        await session.commit()

        unhidden = await repo.unhide_giveaway(giveaway.id)
        await session.commit()

        assert unhidden is not None
        assert unhidden.is_hidden is False


@pytest.mark.asyncio
async def test_mark_entered(test_db):
    """Test marking giveaway as entered."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        giveaway = await repo.create(
            code="GA1", game_name="Game 1", price=50, url="http://test.com"
        )
        await session.commit()

        entered = await repo.mark_entered(giveaway.id)
        await session.commit()

        assert entered is not None
        assert entered.is_entered is True
        assert entered.entered_at is not None


@pytest.mark.asyncio
async def test_mark_entered_with_custom_time(test_db):
    """Test marking giveaway as entered with custom timestamp."""
    async with test_db() as session:
        repo = GiveawayRepository(session)
        custom_time = datetime(2025, 1, 1, 12, 0, 0)

        giveaway = await repo.create(
            code="GA1", game_name="Game 1", price=50, url="http://test.com"
        )
        await session.commit()

        entered = await repo.mark_entered(giveaway.id, entered_at=custom_time)
        await session.commit()

        assert entered.entered_at == custom_time


@pytest.mark.asyncio
async def test_get_expiring_soon(test_db):
    """Test getting giveaways expiring soon."""
    async with test_db() as session:
        repo = GiveawayRepository(session)
        now = datetime.utcnow()

        # Expires in 6 hours
        await repo.create(
            code="SOON",
            game_name="Game 1",
            price=50,
            url="http://test.com/1",
            end_time=now + timedelta(hours=6),
        )

        # Expires in 48 hours
        await repo.create(
            code="LATER",
            game_name="Game 2",
            price=30,
            url="http://test.com/2",
            end_time=now + timedelta(hours=48),
        )

        # Already expired
        await repo.create(
            code="EXPIRED",
            game_name="Game 3",
            price=40,
            url="http://test.com/3",
            end_time=now - timedelta(hours=1),
        )

        await session.commit()

        expiring = await repo.get_expiring_soon(hours=24)

        assert len(expiring) == 1
        assert expiring[0].code == "SOON"


@pytest.mark.asyncio
async def test_get_expiring_soon_excludes_entered(test_db):
    """Test expiring soon excludes already entered giveaways."""
    async with test_db() as session:
        repo = GiveawayRepository(session)
        now = datetime.utcnow()

        await repo.create(
            code="AVAILABLE",
            game_name="Game 1",
            price=50,
            url="http://test.com/1",
            end_time=now + timedelta(hours=6),
            is_entered=False,
        )

        await repo.create(
            code="ENTERED",
            game_name="Game 2",
            price=30,
            url="http://test.com/2",
            end_time=now + timedelta(hours=6),
            is_entered=True,
        )

        await session.commit()

        expiring = await repo.get_expiring_soon(hours=24)

        assert len(expiring) == 1
        assert expiring[0].code == "AVAILABLE"


@pytest.mark.asyncio
async def test_count_active(test_db):
    """Test counting active giveaways."""
    async with test_db() as session:
        repo = GiveawayRepository(session)
        now = datetime.utcnow()

        # 2 active
        await repo.create(
            code="GA1",
            game_name="Game 1",
            price=50,
            url="http://test.com/1",
            end_time=now + timedelta(hours=24),
        )
        await repo.create(
            code="GA2",
            game_name="Game 2",
            price=30,
            url="http://test.com/2",
            end_time=now + timedelta(hours=48),
        )

        # 1 expired
        await repo.create(
            code="EXPIRED",
            game_name="Game 3",
            price=40,
            url="http://test.com/3",
            end_time=now - timedelta(hours=1),
        )

        await session.commit()

        count = await repo.count_active()

        assert count == 2


@pytest.mark.asyncio
async def test_count_entered(test_db):
    """Test counting entered giveaways."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        await repo.create(
            code="GA1",
            game_name="Game 1",
            price=50,
            url="http://test.com/1",
            is_entered=True,
        )
        await repo.create(
            code="GA2",
            game_name="Game 2",
            price=30,
            url="http://test.com/2",
            is_entered=True,
        )
        await repo.create(
            code="GA3",
            game_name="Game 3",
            price=40,
            url="http://test.com/3",
            is_entered=False,
        )

        await session.commit()

        count = await repo.count_entered()

        assert count == 2


@pytest.mark.asyncio
async def test_search_by_game_name(test_db):
    """Test searching giveaways by game name."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        await repo.create(
            code="GA1",
            game_name="Portal 2",
            price=50,
            url="http://test.com/1",
        )
        await repo.create(
            code="GA2",
            game_name="Portal",
            price=30,
            url="http://test.com/2",
        )
        await repo.create(
            code="GA3",
            game_name="Half-Life 2",
            price=40,
            url="http://test.com/3",
        )

        await session.commit()

        results = await repo.search_by_game_name("portal")

        assert len(results) == 2
        assert all("portal" in ga.game_name.lower() for ga in results)


@pytest.mark.asyncio
async def test_search_by_game_name_case_insensitive(test_db):
    """Test game name search is case-insensitive."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        await repo.create(
            code="GA1", game_name="PORTAL 2", price=50, url="http://test.com"
        )

        await session.commit()

        results = await repo.search_by_game_name("portal")

        assert len(results) == 1


@pytest.mark.asyncio
async def test_get_safe_giveaways(test_db):
    """Test getting safe giveaways with high safety scores."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        await repo.create(
            code="SAFE1",
            game_name="Game 1",
            price=50,
            url="http://test.com/1",
            is_safe=True,
            safety_score=95,
        )
        await repo.create(
            code="SAFE2",
            game_name="Game 2",
            price=30,
            url="http://test.com/2",
            is_safe=True,
            safety_score=85,
        )
        await repo.create(
            code="LOW_SCORE",
            game_name="Game 3",
            price=40,
            url="http://test.com/3",
            is_safe=True,
            safety_score=60,
        )

        await session.commit()

        safe = await repo.get_safe_giveaways(min_safety_score=80)

        assert len(safe) == 2
        assert all(ga.safety_score >= 80 for ga in safe)


@pytest.mark.asyncio
async def test_get_safe_giveaways_ordered_by_score(test_db):
    """Test safe giveaways ordered by safety score descending."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        await repo.create(
            code="MEDIUM",
            game_name="Game 1",
            price=50,
            url="http://test.com/1",
            is_safe=True,
            safety_score=85,
        )
        await repo.create(
            code="HIGHEST",
            game_name="Game 2",
            price=30,
            url="http://test.com/2",
            is_safe=True,
            safety_score=95,
        )

        await session.commit()

        safe = await repo.get_safe_giveaways(min_safety_score=80)

        assert len(safe) == 2
        assert safe[0].code == "HIGHEST"


@pytest.mark.asyncio
async def test_get_unsafe_giveaways(test_db):
    """Test getting unsafe giveaways."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        await repo.create(
            code="SAFE",
            game_name="Game 1",
            price=50,
            url="http://test.com/1",
            is_safe=True,
        )
        await repo.create(
            code="UNSAFE1",
            game_name="Game 2",
            price=30,
            url="http://test.com/2",
            is_safe=False,
        )
        await repo.create(
            code="UNSAFE2",
            game_name="Game 3",
            price=40,
            url="http://test.com/3",
            is_safe=False,
        )

        await session.commit()

        unsafe = await repo.get_unsafe_giveaways()

        assert len(unsafe) == 2
        assert all(ga.is_safe is False for ga in unsafe)


@pytest.mark.asyncio
async def test_create_or_update_by_code_creates_new(test_db):
    """Test create_or_update creates new giveaway if not exists."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        giveaway = await repo.create_or_update_by_code(
            code="NEW", game_name="Game 1", price=50, url="http://test.com"
        )
        await session.commit()

        assert giveaway.code == "NEW"
        assert giveaway.game_name == "Game 1"


@pytest.mark.asyncio
async def test_create_or_update_by_code_updates_existing(test_db):
    """Test create_or_update updates existing giveaway."""
    async with test_db() as session:
        repo = GiveawayRepository(session)

        # Create initial
        await repo.create(
            code="EXISTING", game_name="Old Name", price=50, url="http://test.com"
        )
        await session.commit()

        # Update via create_or_update
        updated = await repo.create_or_update_by_code(
            code="EXISTING", game_name="New Name", price=100
        )
        await session.commit()

        assert updated.game_name == "New Name"
        assert updated.price == 100

        # Verify only one record exists
        all_giveaways = await repo.get_all()
        assert len(all_giveaways) == 1
