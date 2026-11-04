"""Unit tests for giveaway API schemas."""


import pytest
from pydantic import ValidationError

from api.schemas.giveaway import (
    AutojoinRegistryResponse,
    CandidatePreviewResponse,
    DecisionResponse,
    GiveawayBase,
    GiveawayEntryRequest,
    GiveawayEntryResponse,
    GiveawayFilter,
    GiveawayList,
    GiveawayResponse,
    GiveawayScanRequest,
    GiveawayScanResponse,
    GiveawayStats,
    LensGiveawaysResponse,
    PolicyPreviewResponse,
)
from core.time import utcnow
from services.eligibility import FILTERS, GATES, registry_as_data


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
        end_time=utcnow(),
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
        discovered_at=utcnow()
    )

    assert giveaway.id == 123
    assert giveaway.discovered_at is not None
    # Joined game genres default to None (game not cached / not fetched)
    assert giveaway.game_genres is None


def test_giveaway_response_game_genres():
    giveaway = GiveawayResponse(
        id=1, code="AbCd1", url="https://www.steamgifts.com/giveaway/AbCd1/",
        game_name="Portal 2", price=50, discovered_at=utcnow(),
        game_genres=["Action", "Indie"],
    )
    assert giveaway.game_genres == ["Action", "Indie"]
    assert giveaway.model_dump()["game_genres"] == ["Action", "Indie"]


def test_giveaway_response_win_chance():
    """win_chance = copies/entries*100, capped at 100, 100 when no entries."""
    def mk(copies, entries):
        return GiveawayResponse(
            id=1, code="GA1", url="test", game_name="G", price=50,
            copies=copies, entries=entries, discovered_at=utcnow(),
        )

    assert mk(1, 0).win_chance == 100.0      # nobody entered yet
    assert mk(1, 4).win_chance == 25.0
    assert mk(1, 10000).win_chance == 0.01
    assert mk(5, 2).win_chance == 100.0      # more copies than entries -> capped
    assert mk(1, 3).win_chance == 33.33      # rounded to 2 decimals
    # Long shots keep meaningful precision instead of collapsing to 0%
    assert mk(1, 25000).win_chance == 0.004
    assert mk(1, 80000).win_chance == 0.0013
    assert mk(1, 10_000_000).win_chance == 0.0001  # display floor

    # win_chance is serialized in API payloads
    assert mk(1, 4).model_dump()["win_chance"] == 25.0


def test_giveaway_list():
    """Test GiveawayList."""
    giveaway1 = GiveawayResponse(
        id=1, code="GA1", url="test", game_name="Game 1", price=50, discovered_at=utcnow()
    )
    giveaway2 = GiveawayResponse(
        id=2, code="GA2", url="test", game_name="Game 2", price=75, discovered_at=utcnow()
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


def _response(**kw):
    base = dict(id=1, code="AbCd1", url="https://www.steamgifts.com/giveaway/AbCd1/", game_name="Portal 2",
                price=50, discovered_at=utcnow())
    base.update(kw)
    return GiveawayResponse(**base)


@pytest.mark.parametrize("reason, detail, label, kind", [
    (None, None, None, None),
    ("eligible", {"priority": "wishlist", "rank": 0, "lifted_by": "wishlist"}, "Joinable", "enter"),
    ("score_below_min", None, "Review score below minimum", "filter"),
    ("score_below_min", {"score": 6, "min_score": 7}, "Review score 6 is below your minimum 7", "filter"),
    ("genre_not_included", {"genres": ["Action"]}, "None of its genres (Action) is on your included list", "filter"),
    ("budget_floor", {"price": 50, "points": 230, "stop_at": 200},
     "Not entered last cycle: 50P would leave 180P, below your 200P floor", "budget"),
    ("cycle_cap", {"cap": 10}, "Not entered last cycle: the 10 per cycle cap was reached", "budget"),
    ("points_accumulating", {"points": 300, "start_at": 350},
     "Not entered last cycle: 300P is below your 350P start threshold", "budget"),
    ("hidden", {}, "Hidden", "gate"),
    ("unsafe", {"safety_score": 10}, "Flagged unsafe or borderline by the safety check", "gate"),
    ("price_above_max", None, "price_above_max", None),
])
def test_giveaway_response_eligibility_label_and_kind(reason, detail, label, kind):
    response = _response(eligibility_reason=reason, eligibility_detail=detail)
    assert response.eligibility_label == label
    assert response.eligibility_kind == kind
    dumped = response.model_dump()
    assert (dumped["eligibility_label"], dumped["eligibility_kind"], dumped["eligibility_detail"]) == (
        label, kind, detail,
    )


def test_eligibility_label_and_kind_are_not_fields():
    """Computed on read: never accepted as input, never a column."""
    assert "eligibility_label" not in GiveawayResponse.model_fields
    assert "eligibility_kind" not in GiveawayResponse.model_fields
    assert "eligibility_detail" in GiveawayResponse.model_fields


def test_eligibility_checked_at_keeps_the_z_suffix():
    from datetime import datetime

    response = _response(eligibility_reason="hidden", eligibility_checked_at=datetime(2026, 11, 1, 12, 0, 0))
    assert response.model_dump()["eligibility_checked_at"] == "2026-11-01T12:00:00Z"


def test_candidate_preview_response_from_a_row():
    from types import SimpleNamespace

    row = SimpleNamespace(**{name: None for name in GiveawayResponse.model_fields})
    row.__dict__.update(id=3, code="Cand1", url="https://www.steamgifts.com/giveaway/Cand1/", game_name="G",
                        price=20, copies=1, entries=0, is_hidden=False, is_entered=False, is_wishlist=True,
                        is_dlc=False, is_won=False, discovered_at=utcnow())
    decision = DecisionResponse(
        code="eligible", label="Joinable", detail={"priority": "wishlist", "rank": 0, "lifted_by": "wishlist"},
        priority="wishlist", rank=0, lifted_by="wishlist",
    )

    candidate = CandidatePreviewResponse(
        decision=decision, **{name: getattr(row, name) for name in GiveawayResponse.model_fields}
    )

    dumped = candidate.model_dump()
    assert dumped["code"] == "Cand1"
    assert dumped["eligibility_reason"] is None and dumped["eligibility_label"] is None
    assert dumped["decision"]["lifted_by"] == "wishlist"
    with pytest.raises(ValidationError):
        CandidatePreviewResponse(**{name: getattr(row, name) for name in GiveawayResponse.model_fields})


def test_policy_preview_and_lens_responses_never_apply_the_budget():
    preview = PolicyPreviewResponse(candidates=[], count=0, pool=0, counts={})
    lens = LensGiveawaysResponse(giveaways=[], count=0, lens="autojoin")
    assert preview.model_dump() == {"candidates": [], "count": 0, "pool": 0, "counts": {}, "budget_applied": False}
    assert lens.model_dump() == {"giveaways": [], "count": 0, "lens": "autojoin", "budget_applied": False}
    with pytest.raises(ValidationError):
        PolicyPreviewResponse(candidates=[], count=0, pool=0, counts={}, budget_applied=True)
    with pytest.raises(ValidationError):
        LensGiveawaysResponse(giveaways=[], count=0, lens="other")


def test_registry_response_round_trips_the_registry():
    data = registry_as_data()
    registry = AutojoinRegistryResponse.model_validate(data)
    assert registry.model_dump() == data
    assert [g.code for g in registry.gates] == [rule.code for rule in GATES]
    assert [f.setting for f in registry.filters] == [rule.setting for rule in FILTERS]
