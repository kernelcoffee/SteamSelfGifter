"""Tests for autojoin eligibility evaluation.

Three layers:
1. The pure evaluator (`evaluate_eligibility`) — every reason code + precedence.
2. Behavior-equivalence — the evaluator's ELIGIBLE set must match the existing
   SQL filter (`GiveawayRepository.get_eligible`) exactly, so wiring it into the
   cycle does NOT change which giveaways get entered.
3. Persistence — a process cycle records a reason on every candidate.
4. Entry order — `priority_sort_key` (wishlist > DLC > ending soon > rest).
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.time import utcnow
from models.base import Base
from models.game import Game
from models.giveaway import Giveaway
from services.eligibility import (
    ELIGIBLE,
    ENTERED,
    EXPIRED,
    GAME_TOO_OLD,
    HIDDEN,
    NO_GAME_DATA,
    PRICE_ABOVE_MAX,
    PRICE_BELOW_MIN,
    REVIEWS_BELOW_MIN,
    SCORE_BELOW_MIN,
    UNSAFE,
    EligibilityCriteria,
    evaluate_eligibility,
    priority_sort_key,
)
from services.game_service import GameService
from services.giveaway_service import GiveawayService

NOW = datetime(2026, 6, 17, 12, 0, 0)


def _gw(**kw):
    """A giveaway stand-in (only the attributes the evaluator reads)."""
    base = dict(
        end_time=NOW + timedelta(days=1),
        is_hidden=False,
        is_entered=False,
        is_safe=None,
        is_wishlist=False,
        is_dlc=False,
        price=50,
        game_id=620,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _game(**kw):
    base = dict(review_score=9, total_reviews=5000, release_date="2020-01-01")
    base.update(kw)
    return SimpleNamespace(**base)


# ----------------------------------------------------------------------------
# 1. Pure evaluator
# ----------------------------------------------------------------------------

def test_eligible_when_all_criteria_pass():
    crit = EligibilityCriteria(min_price=10, min_score=7, min_reviews=1000)
    assert evaluate_eligibility(_gw(), _game(), crit, NOW) == ELIGIBLE


@pytest.mark.parametrize("end_time", [None, NOW - timedelta(hours=1)])
def test_expired(end_time):
    crit = EligibilityCriteria(min_price=10)
    assert evaluate_eligibility(_gw(end_time=end_time), _game(), crit, NOW) == EXPIRED


def test_hidden():
    crit = EligibilityCriteria(min_price=10)
    assert evaluate_eligibility(_gw(is_hidden=True), _game(), crit, NOW) == HIDDEN


def test_entered():
    crit = EligibilityCriteria(min_price=10)
    assert evaluate_eligibility(_gw(is_entered=True), _game(), crit, NOW) == ENTERED


def test_unsafe_and_borderline_excluded_unchecked_passes():
    crit = EligibilityCriteria(min_price=10)
    # is_safe False covers both unsafe and borderline verdicts
    assert evaluate_eligibility(_gw(is_safe=False), _game(), crit, NOW) == UNSAFE
    # Never-checked (NULL) and safe giveaways pass
    assert evaluate_eligibility(_gw(is_safe=None), _game(), crit, NOW) == ELIGIBLE
    assert evaluate_eligibility(_gw(is_safe=True), _game(), crit, NOW) == ELIGIBLE
    # Safety exclusion also applies to wishlist/DLC bypass giveaways
    assert evaluate_eligibility(_gw(is_wishlist=True, is_safe=False), None, crit, NOW) == UNSAFE


def test_price_below_min():
    crit = EligibilityCriteria(min_price=50)
    assert evaluate_eligibility(_gw(price=49), _game(), crit, NOW) == PRICE_BELOW_MIN


def test_price_above_max():
    crit = EligibilityCriteria(min_price=10, max_price=100)
    assert evaluate_eligibility(_gw(price=150), _game(), crit, NOW) == PRICE_ABOVE_MAX


def test_no_game_data_when_criteria_need_it():
    crit = EligibilityCriteria(min_price=10, min_score=7)
    assert evaluate_eligibility(_gw(), None, crit, NOW) == NO_GAME_DATA


def test_missing_game_is_fine_when_no_game_criteria():
    # No score/reviews/age criteria → no game data required.
    crit = EligibilityCriteria(min_price=10)
    assert evaluate_eligibility(_gw(), None, crit, NOW) == ELIGIBLE


def test_score_below_min_including_unknown_zero():
    crit = EligibilityCriteria(min_price=10, min_score=7)
    assert evaluate_eligibility(_gw(), _game(review_score=6), crit, NOW) == SCORE_BELOW_MIN
    # Unknown score is stored as 0 → treated as a failure (intentional).
    assert evaluate_eligibility(_gw(), _game(review_score=0), crit, NOW) == SCORE_BELOW_MIN


def test_reviews_below_min():
    crit = EligibilityCriteria(min_price=10, min_reviews=1000)
    assert evaluate_eligibility(_gw(), _game(total_reviews=999), crit, NOW) == REVIEWS_BELOW_MIN


def test_game_too_old_and_unknown_release_date():
    crit = EligibilityCriteria(min_price=10, max_game_age=3)  # cutoff 2023-01-01
    assert evaluate_eligibility(_gw(), _game(release_date="2010-05-01"), crit, NOW) == GAME_TOO_OLD
    # Missing release date fails the age check (intentional).
    assert evaluate_eligibility(_gw(), _game(release_date=None), crit, NOW) == GAME_TOO_OLD
    # Recent enough passes.
    assert evaluate_eligibility(_gw(), _game(release_date="2024-01-01"), crit, NOW) == ELIGIBLE


def test_wishlist_bypasses_price_and_game_filters():
    # Fails every filter (price, score, reviews, age, even missing game data),
    # but is on the wishlist → eligible.
    crit = EligibilityCriteria(min_price=100, min_score=9, min_reviews=10000, max_game_age=1)
    assert evaluate_eligibility(_gw(is_wishlist=True, price=1), None, crit, NOW) == ELIGIBLE


def test_dlc_bypasses_filters_when_priority_enabled():
    # DLC listings are for owned games: with dlc_priority on, quality and
    # price filters don't apply.
    crit = EligibilityCriteria(min_price=100, min_score=9, min_reviews=10000, dlc_priority=True)
    assert evaluate_eligibility(_gw(is_dlc=True, price=1), None, crit, NOW) == ELIGIBLE


def test_dlc_no_bypass_by_default():
    # dlc_priority defaults to off (dlc_priority_enabled setting drives it).
    crit = EligibilityCriteria(min_price=100)
    assert evaluate_eligibility(_gw(is_dlc=True, price=1), None, crit, NOW) == PRICE_BELOW_MIN


def test_wishlist_no_bypass_when_priority_disabled():
    # With the toggle off, wishlist giveaways pass the same filters as
    # everything else.
    crit = EligibilityCriteria(min_price=100, wishlist_priority=False)
    assert evaluate_eligibility(_gw(is_wishlist=True, price=1), None, crit, NOW) == PRICE_BELOW_MIN


def test_wishlist_still_respects_expired_hidden_entered():
    crit = EligibilityCriteria(min_price=10)
    assert evaluate_eligibility(
        _gw(is_wishlist=True, end_time=NOW - timedelta(hours=1)), None, crit, NOW
    ) == EXPIRED
    assert evaluate_eligibility(_gw(is_wishlist=True, is_hidden=True), None, crit, NOW) == HIDDEN
    assert evaluate_eligibility(_gw(is_wishlist=True, is_entered=True), None, crit, NOW) == ENTERED


def test_precedence_hidden_beats_price_and_score():
    crit = EligibilityCriteria(min_price=100, min_score=10)
    gw = _gw(is_hidden=True, price=1)
    assert evaluate_eligibility(gw, _game(review_score=0), crit, NOW) == HIDDEN


def test_precedence_price_beats_missing_game():
    crit = EligibilityCriteria(min_price=100, min_score=7)
    assert evaluate_eligibility(_gw(price=1), None, crit, NOW) == PRICE_BELOW_MIN


# ----------------------------------------------------------------------------
# 4. Entry order: priority_sort_key (pure, fixed NOW)
# ----------------------------------------------------------------------------

def _priority_pool():
    """Candidate pool in the repository's price-descending order."""
    return [
        _gw(code="far", price=900, end_time=NOW + timedelta(days=3)),
        _gw(code="past_thr", price=500, end_time=NOW + timedelta(minutes=61)),
        _gw(code="noend", price=300, end_time=None),
        _gw(code="wish2", price=40, end_time=NOW + timedelta(days=3), is_wishlist=True),
        _gw(code="dlc2", price=30, end_time=NOW + timedelta(days=3), is_dlc=True),
        _gw(code="soon5", price=20, end_time=NOW + timedelta(minutes=5)),
        _gw(code="dlc", price=15, end_time=NOW + timedelta(minutes=10), is_dlc=True),
        _gw(code="at_thr", price=10, end_time=NOW + timedelta(minutes=60)),
        _gw(code="wish", price=5, end_time=NOW + timedelta(minutes=10), is_wishlist=True),
    ]


def _ordered_codes(pool, criteria, now=NOW):
    return [g.code for g in sorted(pool, key=lambda g: priority_sort_key(g, criteria, now))]


def _legacy_key(g, criteria):
    """The two-element key evaluate_and_get_eligible used before ending-soon."""
    return (
        not (criteria.wishlist_priority and g.is_wishlist),
        not (criteria.dlc_priority and g.is_dlc),
    )


@pytest.mark.parametrize("wishlist, dlc, ending_soon, expected", [
    (False, False, False,
     ["far", "past_thr", "noend", "wish2", "dlc2", "soon5", "dlc", "at_thr", "wish"]),
    (True, False, False,
     ["wish2", "wish", "far", "past_thr", "noend", "dlc2", "soon5", "dlc", "at_thr"]),
    (False, True, False,
     ["dlc2", "dlc", "far", "past_thr", "noend", "wish2", "soon5", "at_thr", "wish"]),
    (True, True, False,
     ["wish2", "wish", "dlc2", "dlc", "far", "past_thr", "noend", "soon5", "at_thr"]),
    # Lifts off: wishlist/DLC rows ending in 10 min are plain and join the
    # ending-soon group; dlc and wish share an end_time so price order holds.
    (False, False, True,
     ["soon5", "dlc", "wish", "at_thr", "far", "past_thr", "noend", "wish2", "dlc2"]),
    (True, False, True,
     ["wish2", "wish", "soon5", "dlc", "at_thr", "far", "past_thr", "noend", "dlc2"]),
    (False, True, True,
     ["dlc2", "dlc", "soon5", "wish", "at_thr", "far", "past_thr", "noend", "wish2"]),
    (True, True, True,
     ["wish2", "wish", "dlc2", "dlc", "soon5", "at_thr", "far", "past_thr", "noend"]),
])
def test_priority_sort_key_all_lift_combinations(wishlist, dlc, ending_soon, expected):
    criteria = EligibilityCriteria(
        wishlist_priority=wishlist,
        dlc_priority=dlc,
        ending_soon_priority=ending_soon,
        ending_soon_threshold_minutes=60,
    )
    pool = _priority_pool()
    order = _ordered_codes(pool, criteria)

    assert order == expected
    # Lifted wishlist/DLC groups keep price order even though the cheaper
    # row in each ends sooner.
    if wishlist:
        assert order.index("wish2") < order.index("wish")
    if dlc:
        assert order.index("dlc2") < order.index("dlc")
    # threshold + 1 minute and end_time None are never lifted: they keep
    # their price position among the rest, after the expensive "far" row.
    assert order.index("far") < order.index("past_thr") < order.index("noend")
    if ending_soon:
        # Exactly at the threshold counts; soonest first inside the group.
        assert order.index("soon5") < order.index("at_thr") < order.index("far")
    else:
        # Toggle off: identical to the previous two-element key.
        legacy = [g.code for g in sorted(pool, key=lambda g: _legacy_key(g, criteria))]
        assert order == legacy


@pytest.mark.parametrize("wishlist", [False, True])
@pytest.mark.parametrize("dlc", [False, True])
@pytest.mark.parametrize("threshold", [5, 60, 10080])
def test_priority_sort_key_toggle_off_matches_legacy_key(wishlist, dlc, threshold):
    criteria = EligibilityCriteria(
        wishlist_priority=wishlist, dlc_priority=dlc,
        ending_soon_priority=False, ending_soon_threshold_minutes=threshold,
    )
    pool = _priority_pool()
    for g in pool:
        key = priority_sort_key(g, criteria, NOW)
        assert key[:2] == _legacy_key(g, criteria)
        assert key[2:] == (True, datetime.min)


def test_priority_sort_key_threshold_boundary():
    criteria = EligibilityCriteria(ending_soon_priority=True, ending_soon_threshold_minutes=60)
    at = _gw(end_time=NOW + timedelta(minutes=60))
    past = _gw(end_time=NOW + timedelta(minutes=61))
    none = _gw(end_time=None)
    assert priority_sort_key(at, criteria, NOW) == (True, True, False, at.end_time)
    assert priority_sort_key(past, criteria, NOW) == (True, True, True, datetime.min)
    assert priority_sort_key(none, criteria, NOW) == (True, True, True, datetime.min)


@pytest.mark.parametrize("threshold", [5, 10080])
def test_priority_sort_key_extreme_thresholds(threshold):
    criteria = EligibilityCriteria(
        ending_soon_priority=True, ending_soon_threshold_minutes=threshold,
    )
    pool = [
        _gw(code="rich_out", price=900, end_time=NOW + timedelta(minutes=threshold + 1)),
        _gw(code="mid_at", price=100, end_time=NOW + timedelta(minutes=threshold)),
        _gw(code="cheap_soonest", price=10, end_time=NOW + timedelta(minutes=1)),
        _gw(code="none", price=5, end_time=None),
    ]
    assert _ordered_codes(pool, criteria) == ["cheap_soonest", "mid_at", "rich_out", "none"]


def test_priority_sort_key_end_time_beats_price_and_ties_keep_price():
    criteria = EligibilityCriteria(ending_soon_priority=True, ending_soon_threshold_minutes=60)
    same_end = NOW + timedelta(minutes=30)
    pool = [
        _gw(code="rich_far", price=900, end_time=NOW + timedelta(days=2)),
        _gw(code="soon_500", price=500, end_time=NOW + timedelta(minutes=20)),
        _gw(code="tie_300", price=300, end_time=same_end),
        _gw(code="tie_200", price=200, end_time=same_end),
        _gw(code="soon_10", price=10, end_time=NOW + timedelta(minutes=2)),
    ]
    assert _ordered_codes(pool, criteria) == [
        "soon_10", "soon_500", "tie_300", "tie_200", "rich_far",
    ]


# ----------------------------------------------------------------------------
# DB-backed fixtures for layers 2 & 3
# ----------------------------------------------------------------------------

@pytest.fixture
async def test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield maker
    await engine.dispose()


async def _seed(session):
    """A mixed pool covering every reason code; returns no value."""
    # The code under test uses the real clock (utcnow()), so seed
    # relative to it — a fixed date would silently expire the whole pool.
    now = utcnow()
    future = now + timedelta(days=2)
    past = now - timedelta(days=2)

    # Games
    session.add_all([
        Game(id=1, name="Great", type="game", review_score=9, total_reviews=5000, release_date="2021-01-01"),
        Game(id=2, name="LowScore", type="game", review_score=4, total_reviews=5000, release_date="2021-01-01"),
        Game(id=3, name="FewReviews", type="game", review_score=9, total_reviews=10, release_date="2021-01-01"),
        Game(id=4, name="Old", type="game", review_score=9, total_reviews=5000, release_date="2005-01-01"),
        Game(id=5, name="Unknown", type="dlc", review_score=0, total_reviews=0, release_date=None),
    ])

    def gw(code, price=50, game_id=1, end=future, hidden=False, entered=False,
           wishlist=False, dlc=False, safe=None):
        return Giveaway(
            code=code, url=f"http://x/{code}", game_name=code, price=price,
            end_time=end, game_id=game_id, is_hidden=hidden, is_entered=entered,
            is_wishlist=wishlist, is_dlc=dlc, is_safe=safe,
        )

    session.add_all([
        gw("good1", price=80, game_id=1),       # eligible
        gw("good2", price=60, game_id=1),       # eligible
        gw("lowscore", game_id=2),              # score below min
        gw("fewrev", game_id=3),                # reviews below min
        gw("old", game_id=4),                   # too old (only when max_game_age set)
        gw("unknown", game_id=5),               # score/reviews 0 → fails
        gw("nogame", game_id=999),              # game_id with no Game row → no_game_data
        gw("nogameid", game_id=None),           # no game_id at all → no_game_data
        gw("cheap", price=5, game_id=1),        # price below min (min_price=10)
        gw("hidden", game_id=1, hidden=True),   # hidden
        gw("entered", game_id=1, entered=True), # entered (excluded from candidates)
        gw("expired", game_id=1, end=past),     # expired (excluded by active filter)
        # Wishlist rows: bypass price/game filters even with bad or missing data
        gw("wishbad", price=1, game_id=2, wishlist=True),      # low price + low score → still eligible
        gw("wishnogame", game_id=None, wishlist=True),         # no game data → still eligible
        gw("wishhidden", game_id=1, hidden=True, wishlist=True),  # hidden beats wishlist
        # DLC row: bypasses filters only when dlc_priority is on
        gw("dlcbad", price=1, game_id=2, dlc=True),            # fails price + score filters
        # Safety rows: is_safe False (unsafe or borderline) is excluded even
        # for wishlist; explicit True and NULL (unchecked) pass
        gw("unsafegw", price=80, game_id=1, safe=False),
        gw("wishunsafe", price=80, game_id=1, wishlist=True, safe=False),
        gw("safegw", price=80, game_id=1, safe=True),          # eligible
    ])
    await session.commit()


def _service(session):
    game_service = GameService(session=session, steam_client=MagicMock())
    return GiveawayService(session, MagicMock(), game_service)


# ----------------------------------------------------------------------------
# 2. Behavior-equivalence: evaluator ELIGIBLE set == SQL get_eligible
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("crit_kwargs", [
    dict(min_price=10, min_score=7, min_reviews=1000),                 # defaults
    dict(min_price=10, min_score=7, min_reviews=1000, max_game_age=5), # + age
    dict(min_price=10),                                                # no game criteria
    dict(min_price=10, max_price=70, min_score=7, min_reviews=1000),   # + max price
    dict(min_price=0, min_score=0, min_reviews=0),                     # zero thresholds
    dict(min_price=10, min_score=7, min_reviews=1000, wishlist_priority=False),  # toggle off
    dict(min_price=10, min_score=7, min_reviews=1000, dlc_priority=True),  # DLC priority on
    # Ending-soon lift: ordering only, the eligible set must not change.
    dict(min_price=10, min_score=7, min_reviews=1000, ending_soon_priority=True),
    dict(min_price=10, min_score=7, min_reviews=1000, dlc_priority=True,
         ending_soon_priority=True, ending_soon_threshold_minutes=10080),
])
@pytest.mark.asyncio
async def test_evaluator_matches_sql_get_eligible(test_db, crit_kwargs):
    async with test_db() as session:
        await _seed(session)
        service = _service(session)

        # get_eligible is the SQL filter and knows nothing about entry order.
        sql_kwargs = {
            k: v for k, v in crit_kwargs.items()
            if k not in ("ending_soon_priority", "ending_soon_threshold_minutes")
        }
        sql_eligible = await service.giveaway_repo.get_eligible(**sql_kwargs)
        sql_codes = {g.code for g in sql_eligible}
        # Guard against vacuous equivalence: every param set is chosen so the
        # seeded pool yields at least one eligible giveaway.
        assert sql_codes, f"seed produced no SQL-eligible giveaways for {crit_kwargs}"

        criteria = EligibilityCriteria(**{
            "min_price": crit_kwargs.get("min_price", 0),
            "max_price": crit_kwargs.get("max_price"),
            "min_score": crit_kwargs.get("min_score"),
            "min_reviews": crit_kwargs.get("min_reviews"),
            "max_game_age": crit_kwargs.get("max_game_age"),
            "wishlist_priority": crit_kwargs.get("wishlist_priority", True),
            "dlc_priority": crit_kwargs.get("dlc_priority", False),
            "ending_soon_priority": crit_kwargs.get("ending_soon_priority", False),
            "ending_soon_threshold_minutes": crit_kwargs.get("ending_soon_threshold_minutes", 60),
        })
        evaluated = await service.evaluate_and_get_eligible(criteria)
        eval_codes = {g.code for g in evaluated}

        assert eval_codes == sql_codes, f"mismatch for {crit_kwargs}"
        assert "wishhidden" not in eval_codes
        if criteria.wishlist_priority:
            # Wishlist rows bypass the filters, so they are always in the set.
            assert {"wishbad", "wishnogame"} <= eval_codes
        else:
            # Toggle off: wishlist rows get no exemption from the filters.
            assert "wishbad" not in eval_codes      # fails price + score filters
            assert "wishnogame" not in eval_codes   # no game data
        if criteria.dlc_priority:
            assert "dlcbad" in eval_codes
        elif (crit_kwargs.get("min_score") or 0) > 0:
            # Without the priority, strict criteria reject it (price + score).
            assert "dlcbad" not in eval_codes

        # Ordering: wishlist first, then DLC, then ending soon, then price
        # desc (active priorities only) — mirror the sort key and require
        # sortedness. All seeded rows share one end_time, so price breaks ties.
        now = utcnow()
        keys = [(*priority_sort_key(g, criteria, now), -g.price) for g in evaluated]
        assert keys == sorted(keys)


@pytest.mark.asyncio
async def test_evaluate_and_get_eligible_lifts_ending_soon(test_db):
    """End to end through the service: the ending-soon lift reorders the
    eligible list (soonest first, after wishlist) without changing the set,
    and with the toggle off the order is the legacy price order."""
    async with test_db() as session:
        now = utcnow()
        session.add(Game(id=1, name="G", type="game", review_score=9,
                         total_reviews=5000, release_date="2021-01-01"))

        def gw(code, price, end, wishlist=False):
            return Giveaway(code=code, url=f"http://x/{code}", game_name=code,
                            price=price, end_time=end, game_id=1, is_wishlist=wishlist)

        session.add_all([
            gw("rich_far", 900, now + timedelta(days=3)),
            gw("wish_far", 5, now + timedelta(days=3), wishlist=True),
            gw("soon_mid", 500, now + timedelta(minutes=30)),
            gw("soon_cheap", 10, now + timedelta(minutes=5)),
        ])
        await session.commit()
        service = _service(session)

        on = EligibilityCriteria(min_price=0, ending_soon_priority=True,
                                 ending_soon_threshold_minutes=60)
        off = EligibilityCriteria(min_price=0)
        on_codes = [g.code for g in await service.evaluate_and_get_eligible(on)]
        off_codes = [g.code for g in await service.evaluate_and_get_eligible(off)]

        assert on_codes == ["wish_far", "soon_cheap", "soon_mid", "rich_far"]
        assert off_codes == ["wish_far", "rich_far", "soon_mid", "soon_cheap"]
        # limit is applied after the sort: the cheap soon row wins the slot.
        limited = await service.evaluate_and_get_eligible(
            EligibilityCriteria(min_price=0, wishlist_priority=False,
                                ending_soon_priority=True), limit=1)
        assert [g.code for g in limited] == ["soon_cheap"]


@pytest.mark.asyncio
async def test_ending_soon_lift_never_bypasses_filters(test_db):
    """Rows ending within the threshold that fail a filter stay ineligible with
    their filter reason recorded; the eligible set is identical with the lift
    on and off, only the order differs."""
    async with test_db() as session:
        now = utcnow()
        soon = now + timedelta(minutes=10)
        far = now + timedelta(days=3)
        session.add_all([
            Game(id=1, name="Great", type="game", review_score=9,
                 total_reviews=5000, release_date="2021-01-01"),
            Game(id=2, name="Bad", type="game", review_score=3,
                 total_reviews=5000, release_date="2021-01-01"),
        ])

        def gw(code, price, end, game_id=1, **kw):
            return Giveaway(code=code, url=f"http://x/{code}", game_name=code,
                            price=price, end_time=end, game_id=game_id, **kw)

        session.add_all([
            gw("far_ok", 300, far),
            gw("soon_ok", 20, soon),
            gw("soon_cheap", 5, soon),                    # price below min
            gw("soon_lowscore", 50, soon, game_id=2),     # score below min
            gw("soon_hidden", 50, soon, is_hidden=True),  # hidden
            gw("soon_unsafe", 50, soon, is_safe=False),   # unsafe
            gw("soon_nogame", 50, soon, game_id=None),    # no game data
        ])
        await session.commit()
        service = _service(session)

        base = dict(min_price=10, min_score=7, min_reviews=1000)
        on = await service.evaluate_and_get_eligible(EligibilityCriteria(
            **base, ending_soon_priority=True, ending_soon_threshold_minutes=60))
        on_codes = [g.code for g in on]
        off_codes = [g.code for g in await service.evaluate_and_get_eligible(
            EligibilityCriteria(**base))]

        assert set(on_codes) == set(off_codes) == {"far_ok", "soon_ok"}
        assert on_codes == ["soon_ok", "far_ok"]
        assert off_codes == ["far_ok", "soon_ok"]

        # The SQL filter agrees with the evaluator's set.
        sql_codes = {g.code for g in await service.giveaway_repo.get_eligible(**base)}
        assert sql_codes == set(on_codes)

        reasons = {
            g.code: g.eligibility_reason
            for g in await service.giveaway_repo.get_active_unentered()
        }
        assert reasons["soon_cheap"] == PRICE_BELOW_MIN
        assert reasons["soon_lowscore"] == SCORE_BELOW_MIN
        assert reasons["soon_hidden"] == HIDDEN
        assert reasons["soon_unsafe"] == UNSAFE
        assert reasons["soon_nogame"] == NO_GAME_DATA


# ----------------------------------------------------------------------------
# 3. Persistence: every candidate gets a recorded reason
# ----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reasons_persisted_for_all_candidates(test_db):
    async with test_db() as session:
        await _seed(session)
        service = _service(session)

        criteria = EligibilityCriteria(min_price=10, min_score=7, min_reviews=1000)
        await service.evaluate_and_get_eligible(criteria)

        # Reload and check stored reasons (entered/expired are not candidates).
        reasons = {
            g.code: g.eligibility_reason
            for g in await service.giveaway_repo.get_all()
        }

        assert reasons["good1"] == ELIGIBLE
        assert reasons["good2"] == ELIGIBLE
        assert reasons["lowscore"] == SCORE_BELOW_MIN
        assert reasons["fewrev"] == REVIEWS_BELOW_MIN
        assert reasons["unknown"] == SCORE_BELOW_MIN
        assert reasons["nogame"] == NO_GAME_DATA
        assert reasons["nogameid"] == NO_GAME_DATA
        assert reasons["cheap"] == PRICE_BELOW_MIN
        assert reasons["hidden"] == HIDDEN
        # 'old' is only too-old when max_game_age is set; here it's eligible.
        assert reasons["old"] == ELIGIBLE
        # Entered and expired giveaways aren't in the active candidate pool.
        assert reasons["entered"] is None
        assert reasons["expired"] is None

        # checked_at recorded for everything that was evaluated.
        checked = {
            g.code: g.eligibility_checked_at
            for g in await service.giveaway_repo.get_all()
        }
        assert checked["good1"] is not None
        assert checked["entered"] is None
