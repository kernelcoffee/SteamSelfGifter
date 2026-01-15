"""Unit tests for entry API schemas."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from api.schemas.entry import (
    EntryBase,
    EntryResponse,
    EntryList,
    EntryFilter,
    EntryStats,
    EntryHistoryItem,
    EntryHistory,
)


def test_entry_base():
    """Test EntryBase creation."""
    entry = EntryBase(
        giveaway_id=123,
        points_spent=50,
        entry_type="manual",
        status="success"
    )

    assert entry.giveaway_id == 123
    assert entry.points_spent == 50
    assert entry.entry_type == "manual"
    assert entry.status == "success"
    assert entry.error_message is None


def test_entry_base_with_error():
    """Test EntryBase with error message."""
    entry = EntryBase(
        giveaway_id=123,
        points_spent=0,
        entry_type="auto",
        status="failed",
        error_message="Insufficient points"
    )

    assert entry.status == "failed"
    assert entry.error_message == "Insufficient points"


def test_entry_base_validates_points():
    """Test EntryBase validates points_spent >= 0."""
    with pytest.raises(ValidationError):
        EntryBase(
            giveaway_id=123,
            points_spent=-10,
            entry_type="manual",
            status="success"
        )


def test_entry_base_validates_entry_type():
    """Test EntryBase validates entry_type."""
    # Valid types
    EntryBase(giveaway_id=1, points_spent=50, entry_type="manual", status="success")
    EntryBase(giveaway_id=1, points_spent=50, entry_type="auto", status="success")
    EntryBase(giveaway_id=1, points_spent=50, entry_type="wishlist", status="success")

    # Invalid type
    with pytest.raises(ValidationError):
        EntryBase(giveaway_id=1, points_spent=50, entry_type="invalid", status="success")


def test_entry_base_validates_status():
    """Test EntryBase validates status."""
    # Valid statuses
    EntryBase(giveaway_id=1, points_spent=50, entry_type="manual", status="success")
    EntryBase(giveaway_id=1, points_spent=50, entry_type="manual", status="failed")

    # Invalid status
    with pytest.raises(ValidationError):
        EntryBase(giveaway_id=1, points_spent=50, entry_type="manual", status="pending")


def test_entry_response():
    """Test EntryResponse."""
    entry = EntryResponse(
        id=456,
        giveaway_id=123,
        points_spent=50,
        entry_type="manual",
        status="success",
        entered_at=datetime.utcnow()
    )

    assert entry.id == 456
    assert entry.giveaway_id == 123
    assert entry.entered_at is not None


def test_entry_list():
    """Test EntryList."""
    entry1 = EntryResponse(
        id=1, giveaway_id=123, points_spent=50, entry_type="manual",
        status="success", entered_at=datetime.utcnow()
    )
    entry2 = EntryResponse(
        id=2, giveaway_id=124, points_spent=75, entry_type="auto",
        status="success", entered_at=datetime.utcnow()
    )

    entry_list = EntryList(entries=[entry1, entry2])

    assert len(entry_list.entries) == 2


def test_entry_filter():
    """Test EntryFilter."""
    filters = EntryFilter(
        entry_type="auto",
        status="success",
        giveaway_id=123
    )

    assert filters.entry_type == "auto"
    assert filters.status == "success"
    assert filters.giveaway_id == 123


def test_entry_filter_all_optional():
    """Test EntryFilter with all fields optional."""
    filters = EntryFilter()

    assert filters.entry_type is None
    assert filters.status is None
    assert filters.giveaway_id is None


def test_entry_filter_validates_entry_type():
    """Test EntryFilter validates entry_type."""
    # Valid
    EntryFilter(entry_type="manual")
    EntryFilter(entry_type="auto")
    EntryFilter(entry_type="wishlist")

    # Invalid
    with pytest.raises(ValidationError):
        EntryFilter(entry_type="invalid")


def test_entry_filter_validates_status():
    """Test EntryFilter validates status."""
    # Valid
    EntryFilter(status="success")
    EntryFilter(status="failed")

    # Invalid
    with pytest.raises(ValidationError):
        EntryFilter(status="pending")


def test_entry_stats():
    """Test EntryStats."""
    stats = EntryStats(
        total=100,
        successful=85,
        failed=15,
        total_points_spent=4250,
        manual_entries=25,
        auto_entries=60,
        wishlist_entries=15,
        success_rate=85.0
    )

    assert stats.total == 100
    assert stats.successful == 85
    assert stats.failed == 15
    assert stats.total_points_spent == 4250
    assert stats.manual_entries == 25
    assert stats.auto_entries == 60
    assert stats.wishlist_entries == 15
    assert stats.success_rate == 85.0


def test_entry_stats_validates_success_rate():
    """Test EntryStats validates success_rate range."""
    # Valid values
    EntryStats(
        total=100, successful=0, failed=100, total_points_spent=0,
        manual_entries=0, auto_entries=0, wishlist_entries=0, success_rate=0.0
    )
    EntryStats(
        total=100, successful=100, failed=0, total_points_spent=5000,
        manual_entries=100, auto_entries=0, wishlist_entries=0, success_rate=100.0
    )

    # Invalid: too high
    with pytest.raises(ValidationError):
        EntryStats(
            total=100, successful=100, failed=0, total_points_spent=5000,
            manual_entries=100, auto_entries=0, wishlist_entries=0, success_rate=101.0
        )


def test_entry_history_item():
    """Test EntryHistoryItem."""
    entry = EntryResponse(
        id=456,
        giveaway_id=123,
        points_spent=50,
        entry_type="manual",
        status="success",
        entered_at=datetime.utcnow()
    )

    history_item = EntryHistoryItem(
        entry=entry,
        game_name="Portal 2",
        game_id=620,
        giveaway_code="AbCd1"
    )

    assert history_item.entry == entry
    assert history_item.game_name == "Portal 2"
    assert history_item.game_id == 620
    assert history_item.giveaway_code == "AbCd1"


def test_entry_history():
    """Test EntryHistory."""
    entry = EntryResponse(
        id=456,
        giveaway_id=123,
        points_spent=50,
        entry_type="manual",
        status="success",
        entered_at=datetime.utcnow()
    )

    history_item = EntryHistoryItem(
        entry=entry,
        game_name="Portal 2",
        game_id=620,
        giveaway_code="AbCd1"
    )

    history = EntryHistory(entries=[history_item])

    assert len(history.entries) == 1
    assert history.entries[0].game_name == "Portal 2"


def test_entry_response_orm_mode():
    """Test EntryResponse has ORM mode enabled."""
    assert EntryResponse.model_config.get("from_attributes") is True
