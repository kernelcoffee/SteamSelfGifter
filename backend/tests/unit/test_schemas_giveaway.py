"""Unit tests for giveaway API schemas."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from api.schemas.giveaway import (
    GiveawayBase,
    GiveawayResponse,
    GiveawayList,
    GiveawayFilter,
    GiveawayScanRequest,
    GiveawayScanResponse,
    GiveawayEntryRequest,
    GiveawayEntryResponse,
    GiveawayStats,
)


def test_giveaway_base():
    """Test GiveawayBase creation."""
    giveaway = GiveawayBase(
        code="AbCd1",
        url="https://www.steamgifts.com/giveaway/AbCd1/",
        game_name="Portal 2",
        price=50
    )

    assert giveaway.code == "AbCd1"
    assert giveaway.game_name == "Portal 2"
    assert giveaway.price == 50
    assert giveaway.copies == 1  # default
    assert giveaway.is_hidden is False  # default
    assert giveaway.is_entered is False  # default


def test_giveaway_base_with_optional_fields():
    """Test GiveawayBase with optional fields."""
    giveaway = GiveawayBase(
        code="AbCd1",
        url="https://www.steamgifts.com/giveaway/AbCd1/",
        game_name="Portal 2",
        price=50,
        game_id=620,
        copies=2,
        end_time=datetime.utcnow(),
        is_safe=True,
        safety_score=95
    )

    assert giveaway.game_id == 620
    assert giveaway.copies == 2
    assert giveaway.is_safe is True
    assert giveaway.safety_score == 95


def test_giveaway_base_validates_price():
    """Test GiveawayBase validates price >= 0."""
    with pytest.raises(ValidationError):
        GiveawayBase(
            code="AbCd1",
            url="https://www.steamgifts.com/giveaway/AbCd1/",
            game_name="Portal 2",
            price=-10
        )


def test_giveaway_base_validates_safety_score():
    """Test GiveawayBase validates safety_score range."""
    # Valid values
    GiveawayBase(code="AbCd1", url="test", game_name="Game", price=50, safety_score=0)
    GiveawayBase(code="AbCd1", url="test", game_name="Game", price=50, safety_score=100)

    # Invalid: too high
    with pytest.raises(ValidationError):
        GiveawayBase(code="AbCd1", url="test", game_name="Game", price=50, safety_score=101)


def test_giveaway_response():
    """Test GiveawayResponse."""
    giveaway = GiveawayResponse(
        id=123,
        code="AbCd1",
        url="https://www.steamgifts.com/giveaway/AbCd1/",
        game_name="Portal 2",
        price=50,
        discovered_at=datetime.utcnow()
    )

    assert giveaway.id == 123
    assert giveaway.discovered_at is not None


def test_giveaway_list():
    """Test GiveawayList."""
    giveaway1 = GiveawayResponse(
        id=1, code="GA1", url="test", game_name="Game 1", price=50, discovered_at=datetime.utcnow()
    )
    giveaway2 = GiveawayResponse(
        id=2, code="GA2", url="test", game_name="Game 2", price=75, discovered_at=datetime.utcnow()
    )

    giveaway_list = GiveawayList(giveaways=[giveaway1, giveaway2])

    assert len(giveaway_list.giveaways) == 2


def test_giveaway_filter():
    """Test GiveawayFilter."""
    filters = GiveawayFilter(
        min_price=50,
        max_price=100,
        min_score=7,
        is_entered=False
    )

    assert filters.min_price == 50
    assert filters.max_price == 100
    assert filters.min_score == 7
    assert filters.is_entered is False


def test_giveaway_filter_validates_min_score():
    """Test GiveawayFilter validates min_score range."""
    # Valid
    GiveawayFilter(min_score=0)
    GiveawayFilter(min_score=10)

    # Invalid: too high
    with pytest.raises(ValidationError):
        GiveawayFilter(min_score=11)


def test_giveaway_scan_request():
    """Test GiveawayScanRequest."""
    request = GiveawayScanRequest(pages=5)

    assert request.pages == 5


def test_giveaway_scan_request_default():
    """Test GiveawayScanRequest default value."""
    request = GiveawayScanRequest()

    assert request.pages == 3


def test_giveaway_scan_request_validates_pages():
    """Test GiveawayScanRequest validates pages range."""
    # Valid
    GiveawayScanRequest(pages=1)
    GiveawayScanRequest(pages=10)

    # Invalid: too low
    with pytest.raises(ValidationError):
        GiveawayScanRequest(pages=0)

    # Invalid: too high
    with pytest.raises(ValidationError):
        GiveawayScanRequest(pages=11)


def test_giveaway_scan_response():
    """Test GiveawayScanResponse."""
    response = GiveawayScanResponse(
        new_count=5,
        updated_count=3,
        total_scanned=8
    )

    assert response.new_count == 5
    assert response.updated_count == 3
    assert response.total_scanned == 8


def test_giveaway_entry_request():
    """Test GiveawayEntryRequest."""
    request = GiveawayEntryRequest(entry_type="auto")

    assert request.entry_type == "auto"


def test_giveaway_entry_request_default():
    """Test GiveawayEntryRequest default value."""
    request = GiveawayEntryRequest()

    assert request.entry_type == "manual"


def test_giveaway_entry_request_validates_type():
    """Test GiveawayEntryRequest validates entry_type."""
    # Valid types
    GiveawayEntryRequest(entry_type="manual")
    GiveawayEntryRequest(entry_type="auto")
    GiveawayEntryRequest(entry_type="wishlist")

    # Invalid type
    with pytest.raises(ValidationError):
        GiveawayEntryRequest(entry_type="invalid")


def test_giveaway_entry_response():
    """Test GiveawayEntryResponse."""
    response = GiveawayEntryResponse(
        success=True,
        points_spent=50,
        message="Successfully entered",
        entry_id=456
    )

    assert response.success is True
    assert response.points_spent == 50
    assert response.entry_id == 456


def test_giveaway_stats():
    """Test GiveawayStats."""
    stats = GiveawayStats(
        total=100,
        active=75,
        entered=25,
        hidden=5
    )

    assert stats.total == 100
    assert stats.active == 75
    assert stats.entered == 25
    assert stats.hidden == 5
