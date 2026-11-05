"""Unit tests for giveaway processor worker."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from core.time import utcnow
from services.eligibility import AutoJoinPolicy, Decision, PriorityItem
from services.giveaway_query import CycleCandidate, CycleResult
from tests.conftest import patch_automation_context


def _autojoin_settings(**overrides):
    """Build a settings mock with sensible autojoin defaults."""
    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"
    mock_settings.autojoin_enabled = True
    mock_settings.autojoin_min_price = 50
    mock_settings.autojoin_min_score = 7
    mock_settings.autojoin_min_reviews = 100
    mock_settings.autojoin_max_game_age = None
    mock_settings.autojoin_start_at = 0
    mock_settings.autojoin_stop_at = 0
    mock_settings.autojoin_priorities = [{"type": "wishlist"}]
    mock_settings.excluded_genres = []
    mock_settings.included_genres = []
    mock_settings.max_entries_per_cycle = 5
    mock_settings.entry_delay_min = 0.01
    mock_settings.entry_delay_max = 0.02
    mock_settings.safety_check_enabled = False
    mock_settings.auto_hide_unsafe = True
    for key, value in overrides.items():
        setattr(mock_settings, key, value)
    return mock_settings


def _mock_giveaway(code="TEST123", price=50, game_name="Test Game",
                   is_wishlist=False, is_dlc=False):
    """Build a giveaway mock with the fields the processor touches: active,
    not hidden, not entered, no safety verdict (no gate fires)."""
    mock_giveaway = MagicMock()
    mock_giveaway.code = code
    mock_giveaway.price = price
    mock_giveaway.game_name = game_name
    mock_giveaway.is_wishlist = is_wishlist
    mock_giveaway.is_dlc = is_dlc
    mock_giveaway.end_time = utcnow() + timedelta(days=1)
    mock_giveaway.is_hidden = False
    mock_giveaway.is_entered = False
    mock_giveaway.is_safe = None
    mock_giveaway.safety_score = None
    return mock_giveaway


def _entry(points_spent=50):
    entry = MagicMock()
    entry.points_spent = points_spent
    return entry


# The eligible detail every mocked candidate carries (unmatched, list [wishlist]).
DETAIL = {"priority": None, "rank": 1, "lifted_by": None}


def _candidate(giveaway, planned="eligible"):
    """An enter candidate as decide_cycle returns it, with its planned code."""
    return CycleCandidate(giveaway=giveaway, decision=Decision(code="eligible", detail=DETAIL), planned=planned)


def _service(points=500, candidates=(), counts=None, total=None):
    """A giveaway service mock: fetch_points -> points, decide_cycle -> the
    candidates (giveaway mocks, planned eligible) in entry order."""
    service = AsyncMock()
    service.fetch_points.return_value = points
    candidates = [_candidate(g) for g in candidates]
    service.decide_cycle.return_value = CycleResult(
        candidates=candidates,
        counts=counts if counts is not None else ({"eligible": len(candidates)} if candidates else {}),
        total=total if total is not None else len(candidates),
    )
    service.enter_giveaway.return_value = _entry()
    return service


async def _run(settings, service, notification_service=None, sleep=None):
    """Run process_giveaways with the mocks; returns (results, ctx)."""
    from workers.processor import process_giveaways

    mocks = {"giveaway_service": service}
    if notification_service is not None:
        mocks["notification_service"] = notification_service
    patcher, ctx = patch_automation_context("workers.processor", settings, **mocks)
    with patcher, \
         patch("workers.processor.event_manager") as mock_event_manager, \
         patch("workers.processor.asyncio.sleep", sleep or AsyncMock()):
        mock_event_manager.broadcast_event = AsyncMock()
        results = await process_giveaways()
    return results, ctx


@pytest.mark.asyncio
async def test_process_giveaways_success():
    """Test successful giveaway processing."""
    service = _service(candidates=[_mock_giveaway()])

    results, ctx = await _run(_autojoin_settings(), service)

    assert results["eligible"] == 1
    assert results["entered"] == 1
    assert results["failed"] == 0
    assert results["points_spent"] == 50
    assert results["skipped"] is False
    # A win check is scheduled after entering anything.
    ctx.scheduler_service.schedule_next_win_check.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_giveaways_not_authenticated():
    """Test processing skipped when not authenticated."""
    from workers.processor import process_giveaways

    mock_settings = MagicMock()
    mock_settings.phpsessid = None

    patcher, ctx = patch_automation_context("workers.processor", mock_settings)

    with patcher:
        results = await process_giveaways()

        assert results["skipped"] is True
        assert results["reason"] == "not_authenticated"


@pytest.mark.asyncio
async def test_process_giveaways_autojoin_disabled():
    """Test processing skipped when autojoin disabled."""
    from workers.processor import process_giveaways

    mock_settings = _autojoin_settings(autojoin_enabled=False)

    patcher, ctx = patch_automation_context("workers.processor", mock_settings)

    with patcher:
        results = await process_giveaways()

        assert results["skipped"] is True
        assert results["reason"] == "autojoin_disabled"


@pytest.mark.asyncio
async def test_process_giveaways_no_eligible():
    """No planned entry: nothing entered, the cycle line carries the decisions."""
    notifications = AsyncMock()
    service = _service(candidates=[], counts={"score_below_min": 3, "hidden": 1}, total=4)

    results, _ = await _run(_autojoin_settings(), service, notifications)

    assert results["eligible"] == 0
    assert results["entered"] == 0
    assert results["skipped"] is False
    assert results["decisions"] == {"score_below_min": 3, "hidden": 1}
    service.enter_giveaway.assert_not_called()
    notifications.log_activity.assert_awaited_once_with(
        level="info", event_type="entry",
        message="Processing completed: No eligible giveaways found",
        details={"decisions": {"score_below_min": 3, "hidden": 1}},
    )


@pytest.mark.asyncio
async def test_process_giveaways_entry_failure():
    """Test processing handles entry failures (enter returns None)."""
    service = _service(candidates=[_mock_giveaway()])
    service.enter_giveaway.return_value = None

    results, _ = await _run(_autojoin_settings(), service)

    assert results["eligible"] == 1
    assert results["entered"] == 0
    assert results["failed"] == 1


@pytest.mark.asyncio
async def test_process_giveaways_entry_error():
    """Test processing handles entry errors (enter raises)."""
    service = _service(candidates=[_mock_giveaway()])
    service.enter_giveaway.side_effect = Exception("Entry error")

    results, _ = await _run(_autojoin_settings(), service)

    assert results["eligible"] == 1
    assert results["entered"] == 0
    assert results["failed"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("auto_hide", [True, False])
async def test_process_giveaways_safety_check_passes_the_hide_flag(auto_hide):
    """With safety checks on, entries go through enter_giveaway_with_safety_check
    with hide_on_steamgifts taken from auto_hide_unsafe."""
    service = _service(candidates=[_mock_giveaway()])
    service.enter_giveaway_with_safety_check.return_value = _entry()

    results, _ = await _run(_autojoin_settings(safety_check_enabled=True, auto_hide_unsafe=auto_hide), service)

    assert results["entered"] == 1
    service.enter_giveaway_with_safety_check.assert_awaited_once_with(
        "TEST123", entry_type="auto", hide_on_steamgifts=auto_hide
    )
    service.enter_giveaway.assert_not_called()


@pytest.mark.asyncio
async def test_process_giveaways_records_the_gate_a_rejected_attempt_hits():
    """An attempt the inline safety check rejects (enter returns None after
    flagging the row is_safe False) is recorded unsafe with the score, not the
    pre-attempt eligible; a plain failed attempt stays eligible."""
    flagged = _mock_giveaway(code="FLAGGED", price=10)
    failed = _mock_giveaway(code="FAILED", price=10)
    service = _service(candidates=[flagged, failed])

    async def safety_rejects(code, **_kwargs):
        if code == "FLAGGED":
            flagged.is_safe = False
            flagged.safety_score = 60
        return None

    service.enter_giveaway_with_safety_check.side_effect = safety_rejects

    results, _ = await _run(_autojoin_settings(safety_check_enabled=True), service)

    assert results["failed"] == 2
    service.record_outcomes.assert_awaited_once_with([
        (flagged, "unsafe", {"safety_score": 60}),
        (failed, "eligible", DETAIL),
    ])
    assert results["decisions"] == {"unsafe": 1, "eligible": 1}


@pytest.mark.asyncio
async def test_process_giveaways_wishlist_entry_type():
    """Wishlist giveaways are recorded with entry_type='wishlist'."""
    service = _service(candidates=[_mock_giveaway(code="WISH1", is_wishlist=True)])

    results, _ = await _run(_autojoin_settings(), service)

    assert results["entered"] == 1
    service.enter_giveaway.assert_awaited_once_with("WISH1", entry_type="wishlist")


@pytest.mark.asyncio
async def test_process_giveaways_dlc_entry_type():
    """DLC giveaways are recorded with entry_type='dlc' (wishlist wins ties)."""
    both = _mock_giveaway(code="BOTH1", is_wishlist=True, is_dlc=True)
    dlc = _mock_giveaway(code="DLC01", is_dlc=True)
    service = _service(candidates=[both, dlc])

    results, _ = await _run(_autojoin_settings(autojoin_priorities=[{"type": "dlc"}]), service)

    assert results["entered"] == 2
    assert service.enter_giveaway.await_args_list == [
        call("BOTH1", entry_type="wishlist"), call("DLC01", entry_type="dlc"),
    ]


@pytest.mark.asyncio
async def test_process_giveaways_builds_the_policy_from_settings():
    """decide_cycle gets the policy built from the settings row and the balance."""
    settings = _autojoin_settings(
        autojoin_priorities=[{"type": "ending_soon", "threshold_minutes": 120}, {"type": "dlc"}],
        excluded_genres=["Sports", "RACING"], included_genres=["RPG"],
        autojoin_start_at=100, autojoin_stop_at=50, max_entries_per_cycle=3, auto_hide_unsafe=False,
    )
    service = _service(points=400)

    await _run(settings, service)

    service.decide_cycle.assert_awaited_once_with(
        AutoJoinPolicy(
            min_price=50, min_score=7, min_reviews=100, max_game_age=None,
            excluded_genres=frozenset({"sports", "racing"}), included_genres=frozenset({"rpg"}),
            priorities=(PriorityItem("ending_soon", threshold_minutes=120), PriorityItem("dlc")),
            start_at=100, stop_at=50, max_entries_per_cycle=3, auto_hide_unsafe=False,
        ),
        400,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("stored", [
    [{"type": "bogus"}],
    [{"type": "wishlist"}, {"type": "wishlist"}],
    [{"type": "ending_soon", "threshold_minutes": 4}],
])
async def test_process_giveaways_fails_closed_on_a_bad_priority_list(stored):
    """An invalid stored list enters nothing, records an error and sends no
    SteamGifts request (not even the points fetch)."""
    notifications = AsyncMock()
    service = _service(candidates=[_mock_giveaway()])

    results, _ = await _run(_autojoin_settings(autojoin_priorities=stored), service, notifications)

    assert results["skipped"] is True
    assert results["reason"] == "invalid_autojoin_priorities"
    service.fetch_points.assert_not_called()
    service.decide_cycle.assert_not_called()
    service.enter_giveaway.assert_not_called()
    service.enter_giveaway_with_safety_check.assert_not_called()
    notifications.log_error.assert_awaited_once()
    assert notifications.log_error.await_args.kwargs["message"].startswith(
        "Auto-join priorities setting is invalid:"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["excluded_genres", "included_genres"])
@pytest.mark.parametrize("corrupt", ["Action", 5])
async def test_process_giveaways_fails_closed_on_a_bad_genre_list(field, corrupt):
    """A hand-edited genre column enters nothing (a string would otherwise
    fold into single letters and let the excluded genre through)."""
    notifications = AsyncMock()
    service = _service(candidates=[_mock_giveaway()])

    results, _ = await _run(_autojoin_settings(**{field: corrupt}), service, notifications)

    assert results["skipped"] is True
    assert results["reason"] == f"invalid_{field}"
    service.fetch_points.assert_not_called()
    service.decide_cycle.assert_not_called()
    service.enter_giveaway.assert_not_called()
    notifications.log_error.assert_awaited_once_with(
        error_type="entry", message=f"Genre list setting is invalid: {field} must be a list of strings"
    )


@pytest.mark.asyncio
async def test_process_giveaways_points_unavailable_still_records_decisions():
    """No balance: the pool is still decided (budget not applied), nothing is
    entered and the failure is logged."""
    notifications = AsyncMock()
    service = _service(points=None, candidates=[], counts={"eligible": 2}, total=2)

    results, _ = await _run(_autojoin_settings(), service, notifications)

    service.decide_cycle.assert_awaited_once()
    assert service.decide_cycle.await_args.args[1] is None
    service.enter_giveaway.assert_not_called()
    assert results["skipped"] is True
    assert results["reason"] == "points_unavailable"
    assert results["decisions"] == {"eligible": 2}
    notifications.log_error.assert_awaited_once_with(
        error_type="entry", message="Points balance unavailable; no entries this cycle"
    )


@pytest.mark.asyncio
async def test_process_giveaways_skipped_below_start_threshold():
    """Below autojoin_start_at nothing is entered, but the pool is decided and
    the Accumulating points line carries the decisions."""
    notifications = AsyncMock()
    service = _service(points=300, candidates=[], counts={"points_accumulating": 4}, total=4)

    results, _ = await _run(
        _autojoin_settings(autojoin_start_at=350, autojoin_stop_at=200), service, notifications
    )

    assert results["skipped"] is True
    assert results["reason"] == "points_below_start_threshold"
    assert results["points_available"] == 300
    assert results["entered"] == 0
    service.decide_cycle.assert_awaited_once()
    service.enter_giveaway.assert_not_called()
    notifications.log_activity.assert_awaited_once_with(
        level="info", event_type="entry",
        message="Accumulating points: 300P is below the 350P start threshold",
        details={"points": 300, "start_at": 350, "decisions": {"points_accumulating": 4}},
    )


@pytest.mark.asyncio
async def test_process_giveaways_budget_floor_skips_expensive():
    """Entries that would draw the balance below autojoin_stop_at are skipped
    and recorded as budget_floor; cheaper giveaways later are still entered."""
    expensive = _mock_giveaway(code="BIG", price=150)
    cheap = _mock_giveaway(code="SMALL", price=50)
    service = _service(candidates=[expensive, cheap])

    results, _ = await _run(_autojoin_settings(autojoin_start_at=350, autojoin_stop_at=400), service)

    # 500 - 150 = 350 < 400 -> BIG skipped; 500 - 50 = 450 >= 400 -> SMALL entered
    assert results["skipped_budget"] == 1
    assert results["entered"] == 1
    service.enter_giveaway.assert_awaited_once_with("SMALL", entry_type="auto")
    service.record_outcomes.assert_awaited_once_with([
        (expensive, "budget_floor", {"price": 150, "points": 500, "stop_at": 400}),
        (cheap, "eligible", DETAIL),
    ])
    assert results["decisions"] == {"eligible": 1, "budget_floor": 1}


@pytest.mark.asyncio
async def test_process_giveaways_budget_tracks_running_balance():
    """The balance decreases as entries succeed, so later entries respect it."""
    first = _mock_giveaway(code="FIRST", price=60)
    second = _mock_giveaway(code="SECOND", price=50)
    service = _service(candidates=[first, second])
    service.enter_giveaway.return_value = _entry(60)

    results, _ = await _run(_autojoin_settings(autojoin_start_at=350, autojoin_stop_at=400), service)

    # FIRST: 500 - 60 = 440 >= 400 -> entered, balance now 440.
    # SECOND: 440 - 50 = 390 < 400 -> skipped by budget.
    assert results["entered"] == 1
    assert results["skipped_budget"] == 1
    service.enter_giveaway.assert_awaited_once_with("FIRST", entry_type="auto")
    service.record_outcomes.assert_awaited_once_with([
        (first, "eligible", DETAIL),
        (second, "budget_floor", {"price": 50, "points": 440, "stop_at": 400}),
    ])


@pytest.mark.asyncio
async def test_process_giveaways_failed_entry_keeps_the_balance():
    """A failed entry spends nothing, so the next candidate is judged on 500."""
    first = _mock_giveaway(code="FIRST", price=60)
    second = _mock_giveaway(code="SECOND", price=50)
    service = _service(candidates=[first, second])
    service.enter_giveaway.side_effect = [None, _entry(50)]

    results, _ = await _run(_autojoin_settings(autojoin_start_at=350, autojoin_stop_at=400), service)

    assert results["failed"] == 1
    assert results["entered"] == 1
    assert service.enter_giveaway.await_args_list == [
        call("FIRST", entry_type="auto"), call("SECOND", entry_type="auto"),
    ]
    service.record_outcomes.assert_awaited_once_with([(first, "eligible", DETAIL), (second, "eligible", DETAIL)])


@pytest.mark.asyncio
async def test_process_giveaways_cap_counts_attempts_in_the_loop():
    """max_entries_per_cycle 2: a failed and a crashed attempt use both slots;
    the third candidate is recorded cycle_cap and never attempted."""
    giveaways = [_mock_giveaway(code=c, price=10) for c in ("A", "B", "C")]
    service = _service(candidates=giveaways)
    service.enter_giveaway.side_effect = [None, RuntimeError("boom")]

    results, _ = await _run(_autojoin_settings(max_entries_per_cycle=2), service, AsyncMock())

    assert [c.args[0] for c in service.enter_giveaway.await_args_list] == ["A", "B"]
    assert results["failed"] == 2
    service.record_outcomes.assert_awaited_once_with([
        (giveaways[0], "eligible", DETAIL),
        (giveaways[1], "eligible", DETAIL),
        (giveaways[2], "cycle_cap", {"cap": 2}),
    ])
    assert results["decisions"] == {"eligible": 2, "cycle_cap": 1}


@pytest.mark.asyncio
async def test_process_giveaways_budget_skip_does_not_use_a_slot():
    """cap 2, points 100, stop 0: the 900P candidate is budget_floor and the
    next two cheap ones are both attempted; the last is cycle_cap."""
    giveaways = [_mock_giveaway(code="BIG", price=900)] + [_mock_giveaway(code=c, price=10) for c in "ABC"]
    service = _service(points=100, candidates=giveaways)
    service.enter_giveaway.return_value = _entry(10)

    results, _ = await _run(_autojoin_settings(max_entries_per_cycle=2), service)

    assert [c.args[0] for c in service.enter_giveaway.await_args_list] == ["A", "B"]
    assert [code for _, code, _ in service.record_outcomes.await_args.args[0]] == [
        "budget_floor", "eligible", "eligible", "cycle_cap"]
    assert results["skipped_budget"] == 1


@pytest.mark.asyncio
async def test_process_giveaways_delays_only_between_attempts():
    """Three attempts: exactly two random delays, none before the first."""
    events = []
    service = _service(candidates=[_mock_giveaway(code=c, price=1) for c in ("A", "B", "C")])

    async def enter(code, entry_type):
        events.append(("enter", code))
        return _entry(1)

    async def sleep(delay):
        events.append(("sleep", 5 <= delay <= 15))

    service.enter_giveaway.side_effect = enter
    settings = _autojoin_settings(entry_delay_min=0, entry_delay_max=None)

    await _run(settings, service, sleep=sleep)

    assert events == [
        ("enter", "A"), ("sleep", True), ("enter", "B"), ("sleep", True), ("enter", "C"),
    ]


@pytest.mark.asyncio
async def test_process_giveaways_completion_log_carries_decisions():
    notifications = AsyncMock()
    service = _service(candidates=[_mock_giveaway()], counts={"eligible": 1, "hidden": 2}, total=3)

    results, _ = await _run(_autojoin_settings(), service, notifications)

    assert results["decisions"] == {"eligible": 1, "hidden": 2}
    assert results["candidates"] == 3
    details = notifications.log_activity.await_args.kwargs["details"]
    assert details["decisions"] == {"eligible": 1, "hidden": 2}
    assert notifications.log_activity.await_args.kwargs["message"].startswith("Processing completed: 1 entered")


@pytest.mark.asyncio
async def test_enter_single_giveaway_success():
    """Test single giveaway entry success."""
    from workers.processor import enter_single_giveaway

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"

    mock_entry = MagicMock()
    mock_entry.points_spent = 50

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.enter_giveaway.return_value = mock_entry

    patcher, ctx = patch_automation_context(
        "workers.processor", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher:
        result = await enter_single_giveaway("TEST123")

        assert result["success"] is True
        assert result["points_spent"] == 50
        assert result["error"] is None

        mock_giveaway_service.enter_giveaway.assert_called_once_with(
            "TEST123",
            entry_type="manual"
        )


@pytest.mark.asyncio
async def test_enter_single_giveaway_not_authenticated():
    """Test single entry when not authenticated."""
    from workers.processor import enter_single_giveaway

    mock_settings = MagicMock()
    mock_settings.phpsessid = None

    patcher, ctx = patch_automation_context("workers.processor", mock_settings)

    with patcher:
        result = await enter_single_giveaway("TEST123")

        assert result["success"] is False
        assert result["error"] == "Not authenticated"


@pytest.mark.asyncio
async def test_enter_single_giveaway_failure():
    """Test single entry failure (enter returns None)."""
    from workers.processor import enter_single_giveaway

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.enter_giveaway.return_value = None

    patcher, ctx = patch_automation_context(
        "workers.processor", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher:
        result = await enter_single_giveaway("TEST123")

        assert result["success"] is False
        assert result["error"] == "Entry failed"


@pytest.mark.asyncio
async def test_enter_single_giveaway_error():
    """Test single entry with error (enter raises)."""
    from workers.processor import enter_single_giveaway

    mock_settings = MagicMock()
    mock_settings.phpsessid = "test_session"

    mock_giveaway_service = AsyncMock()
    mock_giveaway_service.enter_giveaway.side_effect = Exception("API error")

    patcher, ctx = patch_automation_context(
        "workers.processor", mock_settings, giveaway_service=mock_giveaway_service
    )

    with patcher:
        result = await enter_single_giveaway("TEST123")

        assert result["success"] is False
        assert result["error"] == "API error"


# ----------------------------------------------------------------------------
# The real decide_cycle + entry loop (nothing between them mocked)
# ----------------------------------------------------------------------------

async def _real_service_with_pool(session, prices):
    """A real GiveawayService over an in-memory DB with one giveaway per price
    (no game data, all active, unentered), and no network."""
    from datetime import timedelta

    from core.time import utcnow
    from models.giveaway import Giveaway
    from services.game_service import GameService
    from services.giveaway_service import GiveawayService
    from utils.steamgifts_client import SteamGiftsClient

    future = utcnow() + timedelta(days=1)
    for code, price in prices:
        session.add(Giveaway(code=code, url=f"https://www.steamgifts.com/giveaway/{code}/",
                             game_name=code, price=price, end_time=future))
    await session.commit()
    game_service = GameService(session=session, steam_client=MagicMock())
    return GiveawayService(session, MagicMock(spec=SteamGiftsClient), game_service)


@pytest.fixture
async def pipeline_session():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from models.base import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_failed_first_entry_still_attempts_the_affordable_second(pipeline_session):
    """Matrix row 'worker guard | FIRST fails (None) | balance unchanged; SECOND
    attempted if affordable at 500', run through the REAL decide_cycle +
    plan_cycle instead of a mocked enter list.

    points 500, stop_at 400, FIRST 60P, SECOND 50P. Today's loop enters SECOND
    when FIRST fails (500 - 50 = 450 >= 400). The plan pre-marks SECOND
    budget_floor assuming FIRST succeeds, so result.enter is [FIRST] only and
    SECOND is never attempted: a giveaway it should have entered is missed.
    """
    from workers.processor import _process_entries

    service = await _real_service_with_pool(pipeline_session, [("FIRST", 60), ("SECOND", 50)])
    service.fetch_points = AsyncMock(return_value=500)
    service.enter_giveaway = AsyncMock(side_effect=[None, _entry(50)])
    settings = _autojoin_settings(
        autojoin_min_price=0, autojoin_min_score=None, autojoin_min_reviews=None,
        autojoin_start_at=400, autojoin_stop_at=400, max_entries_per_cycle=10,
    )

    with patch("workers.processor.event_manager") as events, patch("workers.processor.asyncio.sleep", AsyncMock()):
        events.broadcast_event = AsyncMock()
        await _process_entries(giveaway_service=service, notification_service=AsyncMock(), settings=settings)

    attempted = [c.args[0] for c in service.enter_giveaway.await_args_list]
    assert attempted == ["FIRST", "SECOND"]
    # The stored decision is what the loop did, not the plan's budget_floor.
    second = await service.giveaway_repo.get_by_code("SECOND")
    await pipeline_session.refresh(second)
    assert second.eligibility_reason == "eligible"


@pytest.mark.asyncio
async def test_successful_first_entry_records_the_real_budget_floor(pipeline_session):
    """Same pool, FIRST succeeds: SECOND is not attempted and is stored
    budget_floor with the balance after FIRST (440P)."""
    from workers.processor import _process_entries

    service = await _real_service_with_pool(pipeline_session, [("FIRST", 60), ("SECOND", 50)])
    service.fetch_points = AsyncMock(return_value=500)
    service.enter_giveaway = AsyncMock(return_value=_entry(60))
    settings = _autojoin_settings(
        autojoin_min_price=0, autojoin_min_score=None, autojoin_min_reviews=None,
        autojoin_start_at=400, autojoin_stop_at=400, max_entries_per_cycle=10,
    )

    with patch("workers.processor.event_manager") as events, patch("workers.processor.asyncio.sleep", AsyncMock()):
        events.broadcast_event = AsyncMock()
        stats = await _process_entries(giveaway_service=service, notification_service=AsyncMock(), settings=settings)

    assert [c.args[0] for c in service.enter_giveaway.await_args_list] == ["FIRST"]
    second = await service.giveaway_repo.get_by_code("SECOND")
    await pipeline_session.refresh(second)
    assert (second.eligibility_reason, second.eligibility_detail) == (
        "budget_floor", {"price": 50, "points": 440, "stop_at": 400})
    assert stats["decisions"] == {"eligible": 1, "budget_floor": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("safety", "auto_hide", "expected"),
    [
        # Borderline: skipped for manual review, not hidden -> unsafe.
        ({"verdict": "borderline", "is_safe": False, "safety_score": 60, "details": ["free"]}, False,
         ("unsafe", {"safety_score": 60})),
        # Unsafe with auto_hide_unsafe off: hidden in this app only -> hidden.
        ({"verdict": "unsafe", "is_safe": False, "safety_score": 10, "details": ["ban"]}, False, ("hidden", {})),
    ],
)
async def test_safety_rejected_attempt_is_stored_with_its_gate(pipeline_session, safety, auto_hide, expected):
    """Through the REAL decide_cycle, safety-checked entry and record_outcomes:
    a giveaway the inline check just refused is not left stored 'eligible'
    (shown 'Joinable') until the next cycle; it carries the gate it now hits."""
    from workers.processor import _process_entries

    service = await _real_service_with_pool(pipeline_session, [("TRAP", 10)])
    service.fetch_points = AsyncMock(return_value=500)
    service.sg_client.check_giveaway_safety = AsyncMock(return_value=safety)
    service.sg_client.enter_giveaway = AsyncMock(side_effect=AssertionError("must not enter"))
    service.sg_client.hide_giveaway = AsyncMock(side_effect=AssertionError("must not hide on SteamGifts"))
    settings = _autojoin_settings(
        autojoin_min_price=0, autojoin_min_score=None, autojoin_min_reviews=None,
        safety_check_enabled=True, auto_hide_unsafe=auto_hide,
    )

    with patch("workers.processor.event_manager") as events, patch("workers.processor.asyncio.sleep", AsyncMock()):
        events.broadcast_event = AsyncMock()
        stats = await _process_entries(giveaway_service=service, notification_service=AsyncMock(), settings=settings)

    trap = await service.giveaway_repo.get_by_code("TRAP")
    await pipeline_session.refresh(trap)
    assert (trap.eligibility_reason, trap.eligibility_detail) == expected
    assert stats["failed"] == 1
    assert stats["decisions"] == {expected[0]: 1}
