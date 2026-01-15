"""Unit tests for GiveawayService."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from models.base import Base
from models.game import Game
from models.giveaway import Giveaway
from models.entry import Entry
from services.giveaway_service import GiveawayService
from services.game_service import GameService
from utils.steamgifts_client import SteamGiftsClient, SteamGiftsError


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
def mock_sg_client():
    """Create mock SteamGifts client."""
    client = MagicMock(spec=SteamGiftsClient)
    return client


@pytest.fixture
def mock_game_service():
    """Create mock GameService."""
    service = MagicMock(spec=GameService)
    service.get_or_fetch_game = AsyncMock(return_value=None)
    return service


@pytest.mark.asyncio
async def test_giveaway_service_init(test_db, mock_sg_client, mock_game_service):
    """Test GiveawayService initialization."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        assert service.session == session
        assert service.sg_client == mock_sg_client
        assert service.game_service == mock_game_service
        assert service.giveaway_repo is not None
        assert service.entry_repo is not None


@pytest.mark.asyncio
async def test_sync_giveaways_new(test_db, mock_sg_client, mock_game_service):
    """Test syncing new giveaways."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Mock SteamGifts response
        mock_sg_client.get_giveaways = AsyncMock(
            return_value=[
                {
                    "code": "AbCd1",
                    "game_name": "Test Game",
                    "price": 50,
                    "copies": 1,
                    "entries": 100,
                    "end_time": datetime.utcnow() + timedelta(hours=24),
                    "thumbnail_url": "https://example.com/image.jpg",
                    "game_id": 730,
                }
            ]
        )

        new, updated = await service.sync_giveaways(pages=1)

        assert new == 1
        assert updated == 0

        # Verify giveaway was created
        giveaway = await service.giveaway_repo.get_by_code("AbCd1")
        assert giveaway is not None
        assert giveaway.game_name == "Test Game"
        assert giveaway.price == 50


@pytest.mark.asyncio
async def test_sync_giveaways_updates_existing(test_db, mock_sg_client, mock_game_service):
    """Test syncing updates existing giveaways."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create existing giveaway
        await service.giveaway_repo.create(
            code="AbCd1",
            url="https://www.steamgifts.com/giveaway/AbCd1/",
            game_name="Old Name",
            price=50,
        )
        await session.commit()

        # Mock updated data
        mock_sg_client.get_giveaways = AsyncMock(
            return_value=[
                {
                    "code": "AbCd1",
                    "game_name": "Old Name",
                    "price": 50,
                    "copies": 1,
                    "entries": 150,  # Updated
                    "end_time": datetime.utcnow() + timedelta(hours=12),
                    "thumbnail_url": None,
                    "game_id": None,
                }
            ]
        )

        new, updated = await service.sync_giveaways(pages=1)

        assert new == 0
        assert updated == 1

        # Verify giveaway was updated
        giveaway = await service.giveaway_repo.get_by_code("AbCd1")
        assert giveaway.end_time is not None


@pytest.mark.asyncio
async def test_sync_giveaways_caches_game_data(test_db, mock_sg_client, mock_game_service):
    """Test sync caches associated game data."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        mock_sg_client.get_giveaways = AsyncMock(
            return_value=[
                {
                    "code": "AbCd1",
                    "game_name": "CS:GO",
                    "price": 50,
                    "game_id": 730,
                }
            ]
        )

        await service.sync_giveaways(pages=1)

        # Verify game service was called
        mock_game_service.get_or_fetch_game.assert_called_once_with(730)


@pytest.mark.asyncio
async def test_sync_giveaways_handles_errors(test_db, mock_sg_client, mock_game_service):
    """Test sync handles SteamGifts errors gracefully."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # First page succeeds, second fails
        mock_sg_client.get_giveaways = AsyncMock(
            side_effect=[
                [{"code": "AbCd1", "game_name": "Test", "price": 50}],
                SteamGiftsError("API error", code="SG_002", details={}),
            ]
        )

        new, updated = await service.sync_giveaways(pages=2)

        # Should have synced first page only
        assert new == 1
        assert updated == 0


@pytest.mark.asyncio
async def test_enter_giveaway_success(test_db, mock_sg_client, mock_game_service):
    """Test successfully entering a giveaway."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create giveaway
        giveaway = await service.giveaway_repo.create(
            code="AbCd1",
            url="https://www.steamgifts.com/giveaway/AbCd1/",
            game_name="Test Game",
            price=50,
        )
        giveaway_id = giveaway.id
        await session.commit()

        # Mock successful entry
        mock_sg_client.enter_giveaway = AsyncMock(return_value=True)

        entry = await service.enter_giveaway("AbCd1", entry_type="auto")

        assert entry is not None
        assert entry.giveaway_id == giveaway_id
        assert entry.points_spent == 50
        assert entry.status == "success"
        assert entry.entry_type == "auto"

        # Verify giveaway marked as entered
        updated_giveaway = await service.giveaway_repo.get_by_code("AbCd1")
        assert updated_giveaway.is_entered is True


@pytest.mark.asyncio
async def test_enter_giveaway_already_entered(test_db, mock_sg_client, mock_game_service):
    """Test entering already-entered giveaway returns existing entry."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create giveaway and entry
        giveaway = await service.giveaway_repo.create(
            code="AbCd1",
            url="https://www.steamgifts.com/giveaway/AbCd1/",
            game_name="Test Game",
            price=50,
        )
        await session.commit()

        existing_entry = await service.entry_repo.create(
            giveaway_id=giveaway.id,
            points_spent=50,
            entry_type="manual",
            status="success",
        )
        await session.commit()

        entry = await service.enter_giveaway("AbCd1")

        # Should return existing entry without calling API
        assert entry.id == existing_entry.id
        mock_sg_client.enter_giveaway.assert_not_called()


@pytest.mark.asyncio
async def test_enter_giveaway_not_found(test_db, mock_sg_client, mock_game_service):
    """Test entering non-existent giveaway."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        entry = await service.enter_giveaway("InvalidCode")

        assert entry is None
        mock_sg_client.enter_giveaway.assert_not_called()


@pytest.mark.asyncio
async def test_enter_giveaway_failure(test_db, mock_sg_client, mock_game_service):
    """Test handling entry failure."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create giveaway
        await service.giveaway_repo.create(
            code="AbCd1",
            url="https://www.steamgifts.com/giveaway/AbCd1/",
            game_name="Test Game",
            price=50,
        )
        await session.commit()

        # Mock failed entry
        mock_sg_client.enter_giveaway = AsyncMock(return_value=False)

        entry = await service.enter_giveaway("AbCd1")

        assert entry is None

        # Should have recorded failed entry
        entries = await service.entry_repo.get_by_status("failed")
        assert len(entries) == 1
        assert entries[0].status == "failed"
        assert entries[0].points_spent == 0


@pytest.mark.asyncio
async def test_enter_giveaway_api_error(test_db, mock_sg_client, mock_game_service):
    """Test handling API error during entry."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create giveaway
        await service.giveaway_repo.create(
            code="AbCd1",
            url="https://www.steamgifts.com/giveaway/AbCd1/",
            game_name="Test Game",
            price=50,
        )
        await session.commit()

        # Mock API error
        mock_sg_client.enter_giveaway = AsyncMock(
            side_effect=SteamGiftsError("Network error", code="SG_002", details={})
        )

        entry = await service.enter_giveaway("AbCd1")

        assert entry is None

        # Should have recorded failed entry with error message
        entries = await service.entry_repo.get_by_status("failed")
        assert len(entries) == 1
        assert "Network error" in entries[0].error_message


@pytest.mark.asyncio
async def test_get_eligible_giveaways(test_db, mock_sg_client, mock_game_service):
    """Test getting eligible giveaways."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create test giveaways
        future_time = datetime.utcnow() + timedelta(hours=24)

        # Eligible
        await service.giveaway_repo.create(
            code="GA1", url="https://www.steamgifts.com/giveaway/GA1/", game_name="Game 1", price=50, end_time=future_time
        )
        # Eligible
        await service.giveaway_repo.create(
            code="GA2", url="https://www.steamgifts.com/giveaway/GA2/", game_name="Game 2", price=100, end_time=future_time
        )
        # Too cheap
        await service.giveaway_repo.create(
            code="GA3", url="https://www.steamgifts.com/giveaway/GA3/", game_name="Game 3", price=10, end_time=future_time
        )
        # Already entered
        ga4 = await service.giveaway_repo.create(
            code="GA4", url="https://www.steamgifts.com/giveaway/GA4/", game_name="Game 4", price=75, end_time=future_time
        )
        ga4.is_entered = True

        await session.commit()

        eligible = await service.get_eligible_giveaways(min_price=50, limit=10)

        assert len(eligible) == 2
        assert all(ga.price >= 50 for ga in eligible)
        assert all(ga.is_entered is False for ga in eligible)


@pytest.mark.asyncio
async def test_get_active_giveaways(test_db, mock_sg_client, mock_game_service):
    """Test getting active giveaways."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create active giveaway
        await service.giveaway_repo.create(
            code="GA1",
            url="https://www.steamgifts.com/giveaway/GA1/",
            game_name="Active",
            price=50,
            end_time=datetime.utcnow() + timedelta(hours=24),
        )
        # Create expired giveaway
        await service.giveaway_repo.create(
            code="GA2",
            url="https://www.steamgifts.com/giveaway/GA2/",
            game_name="Expired",
            price=50,
            end_time=datetime.utcnow() - timedelta(hours=1),
        )
        await session.commit()

        active = await service.get_active_giveaways()

        assert len(active) == 1
        assert active[0].code == "GA1"


@pytest.mark.asyncio
async def test_get_expiring_soon(test_db, mock_sg_client, mock_game_service):
    """Test getting giveaways expiring soon."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        now = datetime.utcnow()

        # Expires in 2 hours
        await service.giveaway_repo.create(
            code="GA1", url="https://www.steamgifts.com/giveaway/GA1/", game_name="Soon", price=50, end_time=now + timedelta(hours=2)
        )
        # Expires in 48 hours
        await service.giveaway_repo.create(
            code="GA2", url="https://www.steamgifts.com/giveaway/GA2/", game_name="Later", price=50, end_time=now + timedelta(hours=48)
        )
        await session.commit()

        expiring = await service.get_expiring_soon(hours=24)

        assert len(expiring) == 1
        assert expiring[0].code == "GA1"


@pytest.mark.asyncio
async def test_hide_giveaway(test_db, mock_sg_client, mock_game_service):
    """Test hiding a giveaway."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        await service.giveaway_repo.create(
            code="AbCd1", url="https://www.steamgifts.com/giveaway/AbCd1/", game_name="Test", price=50
        )
        await session.commit()

        result = await service.hide_giveaway("AbCd1")

        assert result is True

        # Verify it's hidden
        giveaway = await service.giveaway_repo.get_by_code("AbCd1")
        assert giveaway.is_hidden is True


@pytest.mark.asyncio
async def test_search_giveaways(test_db, mock_sg_client, mock_game_service):
    """Test searching giveaways."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        await service.giveaway_repo.create(
            code="GA1", url="https://www.steamgifts.com/giveaway/GA1/", game_name="Portal 2", price=50
        )
        await service.giveaway_repo.create(
            code="GA2", url="https://www.steamgifts.com/giveaway/GA2/", game_name="Portal", price=30
        )
        await service.giveaway_repo.create(
            code="GA3", url="https://www.steamgifts.com/giveaway/GA3/", game_name="Half-Life", price=40
        )
        await session.commit()

        results = await service.search_giveaways("portal")

        assert len(results) == 2
        assert all("portal" in ga.game_name.lower() for ga in results)


@pytest.mark.asyncio
async def test_get_entry_history(test_db, mock_sg_client, mock_game_service):
    """Test getting entry history."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create giveaways
        ga1 = await service.giveaway_repo.create(code="GA1", url="https://www.steamgifts.com/giveaway/GA1/", game_name="Game 1", price=50)
        ga2 = await service.giveaway_repo.create(code="GA2", url="https://www.steamgifts.com/giveaway/GA2/", game_name="Game 2", price=75)
        await session.commit()

        # Create entries
        await service.entry_repo.create(
            giveaway_id=ga1.id, points_spent=50, entry_type="auto", status="success"
        )
        await service.entry_repo.create(
            giveaway_id=ga2.id, points_spent=75, entry_type="manual", status="success"
        )
        await session.commit()

        history = await service.get_entry_history(limit=10)

        assert len(history) == 2


@pytest.mark.asyncio
async def test_get_entry_stats(test_db, mock_sg_client, mock_game_service):
    """Test getting entry statistics."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create giveaway
        ga = await service.giveaway_repo.create(code="GA1", url="https://www.steamgifts.com/giveaway/GA1/", game_name="Game", price=50)
        await session.commit()

        # Create entries
        await service.entry_repo.create(
            giveaway_id=ga.id, points_spent=50, entry_type="auto", status="success"
        )
        await service.entry_repo.create(
            giveaway_id=ga.id + 1, points_spent=0, entry_type="auto", status="failed"
        )
        await session.commit()

        stats = await service.get_entry_stats()

        assert stats["total"] == 2
        assert stats["successful"] == 1
        assert stats["failed"] == 1


@pytest.mark.asyncio
async def test_get_giveaway_stats(test_db, mock_sg_client, mock_game_service):
    """Test getting giveaway statistics."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create active giveaway
        ga1 = await service.giveaway_repo.create(
            code="GA1",
            url="https://www.steamgifts.com/giveaway/GA1/",
            game_name="Active",
            price=50,
            end_time=datetime.utcnow() + timedelta(hours=24),
        )
        # Create entered giveaway
        ga2 = await service.giveaway_repo.create(
            code="GA2",
            url="https://www.steamgifts.com/giveaway/GA2/",
            game_name="Entered",
            price=75,
            end_time=datetime.utcnow() + timedelta(hours=12),
        )
        ga2.is_entered = True

        # Create hidden giveaway
        ga3 = await service.giveaway_repo.create(
            code="GA3", url="https://www.steamgifts.com/giveaway/GA3/", game_name="Hidden", price=30
        )
        ga3.is_hidden = True

        await session.commit()

        stats = await service.get_giveaway_stats()

        assert stats["total"] == 3
        assert stats["active"] == 2
        assert stats["entered"] == 1
        assert stats["hidden"] == 1


# ==================== Safety Detection Service Tests ====================

@pytest.mark.asyncio
async def test_check_giveaway_safety_safe(test_db, mock_sg_client, mock_game_service):
    """Test check_giveaway_safety marks giveaway as safe."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create giveaway
        await service.giveaway_repo.create(
            code="AbCd1",
            url="https://www.steamgifts.com/giveaway/AbCd1/",
            game_name="Safe Game",
            price=50,
        )
        await session.commit()

        # Mock safety check response
        mock_sg_client.check_giveaway_safety = AsyncMock(
            return_value={
                "is_safe": True,
                "safety_score": 100,
                "bad_count": 0,
                "good_count": 0,
                "net_bad": 0,
                "details": [],
            }
        )

        result = await service.check_giveaway_safety("AbCd1")

        assert result["is_safe"] is True
        assert result["safety_score"] == 100

        # Verify giveaway was updated
        giveaway = await service.giveaway_repo.get_by_code("AbCd1")
        assert giveaway.is_safe is True
        assert giveaway.safety_score == 100


@pytest.mark.asyncio
async def test_check_giveaway_safety_unsafe(test_db, mock_sg_client, mock_game_service):
    """Test check_giveaway_safety marks giveaway as unsafe."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create giveaway
        await service.giveaway_repo.create(
            code="Trap1",
            url="https://www.steamgifts.com/giveaway/Trap1/",
            game_name="Trap Game",
            price=50,
        )
        await session.commit()

        # Mock unsafe response
        mock_sg_client.check_giveaway_safety = AsyncMock(
            return_value={
                "is_safe": False,
                "safety_score": 20,
                "bad_count": 4,
                "good_count": 0,
                "net_bad": 4,
                "details": ["ban", "fake", "don't enter"],
            }
        )

        result = await service.check_giveaway_safety("Trap1")

        assert result["is_safe"] is False
        assert result["safety_score"] == 20
        assert "ban" in result["details"]

        # Verify giveaway was updated
        giveaway = await service.giveaway_repo.get_by_code("Trap1")
        assert giveaway.is_safe is False
        assert giveaway.safety_score == 20


# ==================== Hide on SteamGifts Service Tests ====================

@pytest.mark.asyncio
async def test_hide_on_steamgifts_success(test_db, mock_sg_client, mock_game_service):
    """Test hide_on_steamgifts hides game and marks locally."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create giveaway
        await service.giveaway_repo.create(
            code="AbCd1",
            url="https://www.steamgifts.com/giveaway/AbCd1/",
            game_name="Test Game",
            price=50,
        )
        await session.commit()

        # Mock game ID lookup
        mock_sg_client.get_giveaway_game_id = AsyncMock(return_value=12345)
        # Mock hide operation
        mock_sg_client.hide_giveaway = AsyncMock(return_value=True)

        result = await service.hide_on_steamgifts("AbCd1")

        assert result is True

        # Verify hide was called with correct game_id
        mock_sg_client.hide_giveaway.assert_called_once_with(12345)

        # Verify local giveaway was marked as hidden
        giveaway = await service.giveaway_repo.get_by_code("AbCd1")
        assert giveaway.is_hidden is True


@pytest.mark.asyncio
async def test_hide_on_steamgifts_no_game_id(test_db, mock_sg_client, mock_game_service):
    """Test hide_on_steamgifts fails when game_id not found."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create giveaway
        await service.giveaway_repo.create(
            code="AbCd1",
            url="https://www.steamgifts.com/giveaway/AbCd1/",
            game_name="Test Game",
            price=50,
        )
        await session.commit()

        # Mock game ID lookup returns None
        mock_sg_client.get_giveaway_game_id = AsyncMock(return_value=None)

        result = await service.hide_on_steamgifts("AbCd1")

        assert result is False

        # Verify hide was NOT called
        mock_sg_client.hide_giveaway.assert_not_called()


@pytest.mark.asyncio
async def test_hide_on_steamgifts_api_error(test_db, mock_sg_client, mock_game_service):
    """Test hide_on_steamgifts handles API errors."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create giveaway
        await service.giveaway_repo.create(
            code="AbCd1",
            url="https://www.steamgifts.com/giveaway/AbCd1/",
            game_name="Test Game",
            price=50,
        )
        await session.commit()

        # Mock game ID lookup
        mock_sg_client.get_giveaway_game_id = AsyncMock(return_value=12345)
        # Mock hide operation fails
        mock_sg_client.hide_giveaway = AsyncMock(
            side_effect=SteamGiftsError("API error", code="SG_002", details={})
        )

        result = await service.hide_on_steamgifts("AbCd1")

        assert result is False


# ==================== Entry With Safety Check Tests ====================

@pytest.mark.asyncio
async def test_enter_giveaway_with_safety_check_safe(test_db, mock_sg_client, mock_game_service):
    """Test enter_giveaway_with_safety_check enters safe giveaway."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create giveaway
        giveaway = await service.giveaway_repo.create(
            code="AbCd1",
            url="https://www.steamgifts.com/giveaway/AbCd1/",
            game_name="Safe Game",
            price=50,
        )
        giveaway_id = giveaway.id
        await session.commit()

        # Mock safety check - safe
        mock_sg_client.check_giveaway_safety = AsyncMock(
            return_value={
                "is_safe": True,
                "safety_score": 100,
                "bad_count": 0,
                "good_count": 0,
                "net_bad": 0,
                "details": [],
            }
        )
        # Mock successful entry
        mock_sg_client.enter_giveaway = AsyncMock(return_value=True)

        entry = await service.enter_giveaway_with_safety_check("AbCd1", "auto")

        assert entry is not None
        assert entry.giveaway_id == giveaway_id
        assert entry.status == "success"
        assert entry.points_spent == 50

        # Verify entry was called
        mock_sg_client.enter_giveaway.assert_called_once()


@pytest.mark.asyncio
async def test_enter_giveaway_with_safety_check_unsafe(test_db, mock_sg_client, mock_game_service):
    """Test enter_giveaway_with_safety_check blocks unsafe giveaway."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Create giveaway
        await service.giveaway_repo.create(
            code="Trap1",
            url="https://www.steamgifts.com/giveaway/Trap1/",
            game_name="Trap Game",
            price=50,
        )
        await session.commit()

        # Mock safety check - unsafe
        mock_sg_client.check_giveaway_safety = AsyncMock(
            return_value={
                "is_safe": False,
                "safety_score": 20,
                "bad_count": 4,
                "good_count": 0,
                "net_bad": 4,
                "details": ["ban", "fake"],
            }
        )
        # Mock game ID for hiding
        mock_sg_client.get_giveaway_game_id = AsyncMock(return_value=12345)
        mock_sg_client.hide_giveaway = AsyncMock(return_value=True)

        entry = await service.enter_giveaway_with_safety_check("Trap1", "auto")

        # Entry should be None (blocked)
        assert entry is None

        # Verify enter was NOT called
        mock_sg_client.enter_giveaway.assert_not_called()

        # Verify hide was called
        mock_sg_client.hide_giveaway.assert_called_once()

        # Verify failed entry was recorded
        entries = await service.entry_repo.get_by_status("failed")
        assert len(entries) == 1
        assert "Unsafe giveaway" in entries[0].error_message


# ==================== DLC Scanning Service Tests ====================

@pytest.mark.asyncio
async def test_sync_giveaways_dlc_only(test_db, mock_sg_client, mock_game_service):
    """Test sync_giveaways passes dlc_only parameter."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Mock SteamGifts response
        mock_sg_client.get_giveaways = AsyncMock(
            return_value=[
                {
                    "code": "DLC1",
                    "game_name": "Game DLC Pack",
                    "price": 25,
                    "copies": 1,
                    "end_time": datetime.utcnow() + timedelta(hours=24),
                    "thumbnail_url": None,
                    "game_id": None,
                }
            ]
        )

        new, updated = await service.sync_giveaways(pages=1, dlc_only=True)

        assert new == 1

        # Verify dlc_only was passed to client
        mock_sg_client.get_giveaways.assert_called_once_with(
            page=1,
            search_query=None,
            giveaway_type=None,
            dlc_only=True,
            min_copies=None,
        )


@pytest.mark.asyncio
async def test_sync_giveaways_min_copies(test_db, mock_sg_client, mock_game_service):
    """Test sync_giveaways passes min_copies parameter."""
    async with test_db() as session:
        service = GiveawayService(session, mock_sg_client, mock_game_service)

        # Mock SteamGifts response
        mock_sg_client.get_giveaways = AsyncMock(
            return_value=[
                {
                    "code": "Multi1",
                    "game_name": "Multi-Copy Game",
                    "price": 100,
                    "copies": 10,
                    "end_time": datetime.utcnow() + timedelta(hours=24),
                    "thumbnail_url": None,
                    "game_id": None,
                }
            ]
        )

        new, updated = await service.sync_giveaways(pages=1, min_copies=5)

        assert new == 1

        # Verify min_copies was passed to client
        mock_sg_client.get_giveaways.assert_called_once_with(
            page=1,
            search_query=None,
            giveaway_type=None,
            dlc_only=False,
            min_copies=5,
        )
