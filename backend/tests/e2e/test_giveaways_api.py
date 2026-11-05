"""End-to-end tests for giveaway endpoints: game_genres enrichment and the auto-join engine endpoints."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.game import Game
from models.giveaway import Giveaway
from repositories.settings import SettingsRepository
from services.game_service import GameService


async def _seed(async_engine, rows: list[object]) -> None:
    """Insert rows straight into the test database the client uses."""
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        session.add_all(rows)
        await session.commit()


def _game(app_id: int, genres: list[str] | None) -> Game:
    """A cached game refreshed just now, so enrichment never calls Steam."""
    return Game(
        id=app_id,
        name=f"Game {app_id}",
        type="game",
        genres=genres,
        categories=[],
        last_refreshed_at=datetime.now(UTC),
    )


def _giveaway(code: str, game_id: int | None, *, is_entered: bool = False) -> Giveaway:
    now = datetime.now(UTC)
    return Giveaway(
        code=code,
        url=f"https://www.steamgifts.com/giveaway/{code}/",
        game_id=game_id,
        game_name=f"Giveaway {code}",
        price=10,
        end_time=now + timedelta(days=1),
        is_entered=is_entered,
        entered_at=now if is_entered else None,
    )


@pytest.mark.asyncio
async def test_get_giveaway_by_code_includes_game_genres(test_client: AsyncClient, async_engine):
    """GET /giveaways/{code} carries the cached game's genres; no game_id
    gives null."""
    await _seed(async_engine, [_game(620, ["Action"])])
    await _seed(async_engine, [_giveaway("ABCDE", 620), _giveaway("NOGME", None)])

    response = await test_client.get("/api/v1/giveaways/ABCDE")
    assert response.status_code == 200
    assert response.json()["data"]["game_genres"] == ["Action"]

    response = await test_client.get("/api/v1/giveaways/NOGME")
    assert response.status_code == 200
    assert response.json()["data"]["game_genres"] is None


@pytest.mark.asyncio
async def test_get_entered_giveaways_route(test_client: AsyncClient, async_engine):
    """GET /giveaways/entered is a list of entered giveaways with
    game_genres, not a lookup of the giveaway code 'entered'."""
    await _seed(async_engine, [_game(620, ["Action", "Indie"])])
    await _seed(async_engine, [
        _giveaway("ENTR1", 620, is_entered=True),
        _giveaway("OPEN1", 620),
    ])

    response = await test_client.get("/api/v1/giveaways/entered")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["count"] == 1
    assert [g["code"] for g in data["giveaways"]] == ["ENTR1"]
    assert data["giveaways"][0]["game_genres"] == ["Action", "Indie"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/api/v1/giveaways",
    "/api/v1/giveaways/active",
    "/api/v1/giveaways/wishlist",
    "/api/v1/giveaways/dlc",
    "/api/v1/giveaways/won",
])
async def test_enriched_list_endpoints_carry_game_genres(
    test_client: AsyncClient, async_engine, path
):
    """Every enriched list endpoint exposes game_genres: the cached list
    (including []), and null for genres not fetched yet or no game_id."""
    await _seed(async_engine, [
        _game(620, ["Action", "Indie"]),
        _game(621, []),
        _game(622, None),
    ])
    rows = []
    for code, game_id in [("GACTN", 620), ("GEMPT", 621), ("GNULL", 622), ("GNOID", None)]:
        gw = _giveaway(code, game_id)
        gw.is_wishlist = True
        gw.is_dlc = True
        gw.is_won = True
        gw.won_at = datetime.now(UTC)
        rows.append(gw)
    await _seed(async_engine, rows)

    response = await test_client.get(path)

    assert response.status_code == 200
    by_code = {g["code"]: g for g in response.json()["data"]["giveaways"]}
    assert set(by_code) == {"GACTN", "GEMPT", "GNULL", "GNOID"}
    assert by_code["GACTN"]["game_genres"] == ["Action", "Indie"]
    assert by_code["GEMPT"]["game_genres"] == []
    assert by_code["GNULL"]["game_genres"] is None
    assert by_code["GNOID"]["game_genres"] is None
    for giveaway in by_code.values():
        assert "game_genres" in giveaway


# ==================== Auto-join engine endpoints ====================

GIVEAWAY_FIELDS = {
    "id", "code", "url", "game_id", "game_name", "price", "copies", "entries", "end_time", "is_hidden",
    "is_entered", "is_wishlist", "is_dlc", "is_won", "is_safe", "safety_score", "win_chance", "discovered_at",
    "entered_at", "won_at", "game_thumbnail", "game_genres", "game_review_score", "game_total_reviews",
    "game_review_summary", "eligibility_reason", "eligibility_checked_at", "eligibility_detail",
    "eligibility_label", "eligibility_kind",
}


def _scored_game(app_id: int, score: int, genres: list[str] | None = None) -> Game:
    return Game(
        id=app_id, name=f"Game {app_id}", type="game", genres=genres or ["RPG"], categories=[],
        review_score=score, total_reviews=5000, release_date="2024-01-01", last_refreshed_at=datetime.now(UTC),
    )


def _pool_giveaway(code: str, price: int, game_id: int | None, *, minutes: int = 24 * 60, **flags) -> Giveaway:
    return Giveaway(
        code=code, url=f"https://www.steamgifts.com/giveaway/{code}/", game_id=game_id,
        game_name=f"Giveaway {code}", price=price, entries=flags.pop("entries", 0),
        end_time=datetime.now(UTC) + timedelta(minutes=minutes), **flags,
    )


async def _seed_engine_pool(async_engine) -> None:
    """good9 (score 9), meh6 (score 6), wish6 (wishlist, score 6), dlc6 (dlc,
    score 6), cheap (price 5), hidden, entered, uncached (game not cached)."""
    await _seed(async_engine, [_scored_game(1, 9), _scored_game(2, 6)])
    await _seed(async_engine, [
        _pool_giveaway("GOOD9", 90, 1, minutes=600),
        _pool_giveaway("MEH6", 80, 2, minutes=60),
        _pool_giveaway("WISH6", 70, 2, minutes=300, is_wishlist=True),
        _pool_giveaway("DLC06", 65, 2, minutes=400, is_dlc=True),
        _pool_giveaway("GOOD2", 50, 1, minutes=30, is_safe=None),
        _pool_giveaway("CHEAP", 5, 1),
        _pool_giveaway("HIDDN", 75, 1, is_hidden=True),
        _pool_giveaway("ENTRD", 85, 1, is_entered=True),
        _pool_giveaway("UNCHD", 40, 999),
    ])


def _policy_body(**overrides) -> dict:
    body = {
        "autojoin_min_price": 10, "autojoin_min_score": 7, "autojoin_min_reviews": None,
        "autojoin_max_game_age": None, "excluded_genres": [], "included_genres": [],
        "autojoin_priorities": [{"type": "wishlist"}],
    }
    body.update(overrides)
    return body


async def _stored_eligibility(test_client: AsyncClient, code: str) -> tuple:
    """The stored decision as GET /giveaways/{code} returns it."""
    data = (await test_client.get(f"/api/v1/giveaways/{code}")).json()["data"]
    return data["eligibility_reason"], data["eligibility_detail"], data["eligibility_checked_at"]


async def _stored_rows(async_engine) -> dict[str, tuple]:
    """Every row's stored decision, read from the database directly."""
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        rows = (await session.execute(select(Giveaway))).scalars().all()
        return {
            row.code: (row.eligibility_reason, row.eligibility_detail, row.eligibility_checked_at) for row in rows
        }


async def _corrupt_stored_priorities(async_engine) -> None:
    await _corrupt_stored_column(async_engine, "autojoin_priorities", [{"type": "bogus"}])


async def _corrupt_stored_column(async_engine, field: str, value: object) -> None:
    """Write a policy column the API would refuse (a manual database edit)."""
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        settings = await SettingsRepository(session).get_settings()
        setattr(settings, field, value)
        await session.commit()


@pytest.fixture
def no_outbound(monkeypatch):
    """Fail on any real HTTP request (SteamGifts or Steam) and any Steam lookup."""
    calls: list[str] = []

    async def refuse(self, request):
        calls.append(str(request.url))
        raise AssertionError(f"outbound request to {request.url}")

    async def refuse_lookup(*args, **kwargs):
        calls.append("lookup")
        raise AssertionError("Steam lookup")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)
    monkeypatch.setattr(GameService, "lookup_game", refuse_lookup)
    monkeypatch.setattr(GameService, "get_or_fetch_game", refuse_lookup)
    return calls


@pytest.mark.asyncio
async def test_registry_is_served_before_the_code_route(test_client: AsyncClient, no_outbound):
    response = await test_client.get("/api/v1/giveaways/registry")

    assert response.status_code == 200
    data = response.json()["data"]
    assert [g["code"] for g in data["gates"]] == ["expired", "hidden", "entered", "unsafe"]
    assert [(f["code"], f["setting"]) for f in data["filters"]] == [
        ("price_below_min", "autojoin_min_price"), ("genre_excluded", "excluded_genres"),
        ("genre_not_included", "included_genres"), ("no_game_data", None),
        ("score_below_min", "autojoin_min_score"), ("reviews_below_min", "autojoin_min_reviews"),
        ("game_too_old", "autojoin_max_game_age"),
    ]
    assert [o["code"] for o in data["outcomes"]] == ["eligible", "budget_floor", "cycle_cap", "points_accumulating"]
    assert [(p["type"], p["exempt_from_filters"], p["params"]) for p in data["priority_types"]] == [
        ("wishlist", True, []), ("dlc", True, []),
        ("ending_soon", False, [{"name": "threshold_minutes", "min": 5, "max": 10080, "default": 60}]),
    ]
    assert data["limits"] == {"genre_max_items": 50, "genre_max_length": 64, "max_priority_items": 3}
    assert "PHPSESSID" not in response.text and "xsrf" not in response.text.lower()
    assert no_outbound == []


@pytest.mark.asyncio
async def test_preview_uses_the_body_and_persists_nothing(test_client: AsyncClient, async_engine, no_outbound):
    await _seed_engine_pool(async_engine)
    await test_client.put("/api/v1/settings", json={"autojoin_min_score": 7, "phpsessid": "secret-session"})
    before = await _stored_rows(async_engine)

    response = await test_client.post("/api/v1/giveaways/preview?limit=20", json=_policy_body(autojoin_min_score=3))

    assert no_outbound == []  # even with a session configured, SteamGifts is never contacted
    assert response.status_code == 200
    data = response.json()["data"]
    codes = [c["code"] for c in data["candidates"]]
    # MEH6 and DLC06 (score 6) pass the body's minimum 3; the saved minimum is 7
    assert codes == ["WISH6", "GOOD9", "MEH6", "DLC06", "GOOD2"]
    assert data["count"] == 5
    assert data["pool"] == 8  # active, not entered, hidden included
    assert sum(data["counts"].values()) == data["pool"]
    assert data["counts"]["hidden"] == 1
    assert data["budget_applied"] is False
    for candidate in data["candidates"]:
        assert set(candidate) == GIVEAWAY_FIELDS | {"decision"}
        assert candidate["decision"]["code"] == "eligible"
        assert set(candidate["decision"]) == {"code", "label", "detail", "priority", "rank", "lifted_by"}
    assert "secret-session" not in response.text
    assert (await test_client.get("/api/v1/settings")).json()["data"]["autojoin_min_score"] == 7
    assert await _stored_rows(async_engine) == before
    assert before["MEH6"] == (None, None, None)


@pytest.mark.asyncio
async def test_preview_entry_order_and_decision(test_client: AsyncClient, async_engine, no_outbound):
    await _seed_engine_pool(async_engine)

    response = await test_client.post(
        "/api/v1/giveaways/preview",
        json=_policy_body(autojoin_min_score=None, autojoin_priorities=[
            {"type": "dlc"}, {"type": "wishlist"}, {"type": "ending_soon", "threshold_minutes": 90},
        ]),
    )

    data = response.json()["data"]
    assert [c["code"] for c in data["candidates"]] == ["DLC06", "WISH6", "GOOD2", "MEH6", "GOOD9", "UNCHD"]
    wish = data["candidates"][1]
    assert wish["decision"] == {
        "code": "eligible", "label": "Joinable", "detail": {"priority": "wishlist", "rank": 1, "lifted_by": "wishlist"},
        "priority": "wishlist", "rank": 1, "lifted_by": "wishlist",
    }
    assert data["candidates"][-1]["decision"]["priority"] is None


@pytest.mark.asyncio
async def test_preview_limit_slices_but_count_is_total(test_client: AsyncClient, async_engine, no_outbound):
    await _seed_engine_pool(async_engine)

    data = (await test_client.post("/api/v1/giveaways/preview?limit=1", json=_policy_body())).json()["data"]

    assert len(data["candidates"]) == 1
    assert data["count"] == 3  # WISH6 (lifted), GOOD9, GOOD2


@pytest.mark.asyncio
async def test_preview_uncached_game_is_returned_without_a_fetch(test_client: AsyncClient, async_engine, no_outbound):
    await _seed_engine_pool(async_engine)

    data = (await test_client.post(
        "/api/v1/giveaways/preview", json=_policy_body(autojoin_min_score=None)
    )).json()["data"]

    [uncached] = [c for c in data["candidates"] if c["code"] == "UNCHD"]
    assert (uncached["game_genres"], uncached["game_review_score"], uncached["game_thumbnail"]) == (None, None, None)
    [good] = [c for c in data["candidates"] if c["code"] == "GOOD9"]
    assert good["game_review_score"] == 9
    assert no_outbound == []


@pytest.mark.asyncio
@pytest.mark.parametrize("body, query", [
    ({k: v for k, v in _policy_body().items() if k != "included_genres"}, ""),
    ({k: v for k, v in _policy_body().items() if k != "autojoin_min_score"}, ""),
    (_policy_body(autojoin_min_score=11), ""),
    (_policy_body(autojoin_priorities=[{"type": "ending_soon", "threshold_minutes": 4}]), ""),
    (_policy_body(autojoin_priorities=[{"type": "dlc"}, {"type": "dlc"}]), ""),
    (_policy_body(included_genres=["x" * 65]), ""),
    (_policy_body(), "?limit=0"),
    (_policy_body(), "?limit=101"),
])
async def test_preview_validation_is_422_and_writes_nothing(test_client: AsyncClient, async_engine, body, query):
    await _seed_engine_pool(async_engine)
    settings_before = (await test_client.get("/api/v1/settings")).json()["data"]

    response = await test_client.post(f"/api/v1/giveaways/preview{query}", json=body)

    assert response.status_code == 422
    settings_after = (await test_client.get("/api/v1/settings")).json()["data"]
    assert settings_after == settings_before
    assert await _stored_eligibility(test_client, "GOOD9") == (None, None, None)


@pytest.mark.asyncio
async def test_preview_ignores_extra_keys_and_a_corrupt_stored_list(test_client: AsyncClient, async_engine):
    await _seed_engine_pool(async_engine)
    await _corrupt_stored_priorities(async_engine)

    response = await test_client.post("/api/v1/giveaways/preview", json=_policy_body(autojoin_enabled=True))

    assert response.status_code == 200
    assert response.json()["data"]["count"] == 3


@pytest.mark.asyncio
async def test_eligible_matches_preview_of_the_saved_policy(test_client: AsyncClient, async_engine, no_outbound):
    await _seed_engine_pool(async_engine)
    body = _policy_body(autojoin_min_score=7, autojoin_priorities=[{"type": "dlc"}])
    await test_client.put("/api/v1/settings", json=body)

    eligible = (await test_client.get("/api/v1/giveaways/eligible?limit=20")).json()["data"]
    preview = (await test_client.post("/api/v1/giveaways/preview?limit=20", json=body)).json()["data"]

    assert [c["code"] for c in eligible["candidates"]] == [c["code"] for c in preview["candidates"]]
    assert [c["code"] for c in eligible["candidates"]] == ["DLC06", "GOOD9", "GOOD2"]
    assert (eligible["count"], eligible["pool"], eligible["counts"]) == (
        preview["count"], preview["pool"], preview["counts"])
    assert eligible["budget_applied"] is False
    assert "giveaways" not in eligible
    assert "MEH6" not in [c["code"] for c in eligible["candidates"]]  # fails the saved min_score
    assert no_outbound == []
    assert await _stored_eligibility(test_client, "GOOD9") == (None, None, None)


@pytest.mark.asyncio
async def test_eligible_with_a_corrupt_stored_list_is_a_configuration_error(test_client: AsyncClient, async_engine):
    await _seed_engine_pool(async_engine)
    await _corrupt_stored_priorities(async_engine)

    response = await test_client.get("/api/v1/giveaways/eligible")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "CONFIG_002"
    assert "unknown priority type 'bogus'" in error["message"]
    assert await _stored_eligibility(test_client, "GOOD9") == (None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 101])
async def test_eligible_limit_bounds(test_client: AsyncClient, limit):
    assert (await test_client.get(f"/api/v1/giveaways/eligible?limit={limit}")).status_code == 422


@pytest.mark.asyncio
async def test_browse_not_entered_applies_no_policy(test_client: AsyncClient, async_engine):
    await _seed_engine_pool(async_engine)
    await _seed(async_engine, [_pool_giveaway("EXPRD", 99, 1, minutes=-60)])
    await test_client.put("/api/v1/settings", json={"autojoin_min_score": 7})

    data = (await test_client.get("/api/v1/giveaways?is_entered=false")).json()["data"]

    codes = [g["code"] for g in data["giveaways"]]
    assert "MEH6" in codes and "CHEAP" in codes
    assert {"HIDDN", "ENTRD", "EXPRD"}.isdisjoint(codes)
    assert codes == ["GOOD9", "MEH6", "WISH6", "DLC06", "GOOD2", "UNCHD", "CHEAP"]


@pytest.mark.asyncio
async def test_giveaway_responses_carry_the_eligibility_fields(test_client: AsyncClient, async_engine):
    await _seed(async_engine, [_scored_game(1, 6)])
    row = _pool_giveaway("SCORD", 50, 1)
    row.eligibility_reason = "score_below_min"
    row.eligibility_detail = {"score": 6, "min_score": 7}
    row.eligibility_checked_at = datetime(2026, 11, 1, 12, 0, 0)
    await _seed(async_engine, [row, _pool_giveaway("NEVER", 50, 1)])

    scored = (await test_client.get("/api/v1/giveaways/SCORD")).json()["data"]
    never = (await test_client.get("/api/v1/giveaways/NEVER")).json()["data"]

    assert scored["eligibility_detail"] == {"score": 6, "min_score": 7}
    assert scored["eligibility_label"] == "Review score 6 is below your minimum 7"
    assert scored["eligibility_kind"] == "filter"
    assert scored["eligibility_checked_at"] == "2026-11-01T12:00:00Z"
    assert (never["eligibility_label"], never["eligibility_kind"], never["eligibility_detail"]) == (None, None, None)


# ==================== Auto-join lens ====================

@pytest.mark.asyncio
async def test_active_lens_returns_live_candidates_in_entry_order(test_client: AsyncClient, async_engine, no_outbound):
    await _seed_engine_pool(async_engine)
    await test_client.put("/api/v1/settings", json={"autojoin_min_score": 7})

    lens = (await test_client.get("/api/v1/giveaways/active?lens=autojoin")).json()["data"]
    assert no_outbound == []
    plain = (await test_client.get("/api/v1/giveaways/active")).json()["data"]

    assert set(plain) == {"giveaways", "count"}
    assert "MEH6" in [g["code"] for g in plain["giveaways"]]
    assert [g["code"] for g in lens["giveaways"]] == ["WISH6", "GOOD9", "GOOD2"]
    assert (lens["count"], lens["lens"], lens["budget_applied"]) == (3, "autojoin", False)
    assert all(g["decision"]["code"] == "eligible" for g in lens["giveaways"])
    assert "ENTRD" not in [g["code"] for g in lens["giveaways"]]


@pytest.mark.asyncio
async def test_active_lens_paginates_the_candidates(test_client: AsyncClient, async_engine):
    await _seed_engine_pool(async_engine)
    await test_client.put("/api/v1/settings", json={"autojoin_min_score": None, "autojoin_min_reviews": None})

    full = (await test_client.get("/api/v1/giveaways/active?lens=autojoin")).json()["data"]
    page = (await test_client.get("/api/v1/giveaways/active?lens=autojoin&limit=2&offset=2")).json()["data"]

    assert full["count"] == 6
    assert [g["code"] for g in page["giveaways"]] == [g["code"] for g in full["giveaways"][2:4]]
    assert page["count"] == 6


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/giveaways/active", "/api/v1/giveaways/wishlist", "/api/v1/giveaways/dlc"])
async def test_lens_rejects_unknown_values(test_client: AsyncClient, path):
    assert (await test_client.get(f"{path}?lens=foo")).status_code == 422


@pytest.mark.asyncio
async def test_active_lens_intersects_browse_filters(test_client: AsyncClient, async_engine):
    await _seed_engine_pool(async_engine)
    await test_client.put("/api/v1/settings", json={"autojoin_min_score": 7})

    base = [g["code"] for g in (await test_client.get("/api/v1/giveaways/active?lens=autojoin")).json()["data"]["giveaways"]]
    safe = (await test_client.get("/api/v1/giveaways/active?lens=autojoin&is_safe=true")).json()["data"]
    soon = (await test_client.get("/api/v1/giveaways/active?lens=autojoin&ending_within=120")).json()["data"]

    assert "GOOD2" in base
    assert safe["giveaways"] == [] and safe["count"] == 0  # every candidate is is_safe null
    assert [g["code"] for g in soon["giveaways"]] == ["GOOD2"]  # ends in 30 min; GOOD9 in 600


@pytest.mark.asyncio
async def test_wishlist_lens_intersects_min_chance(test_client: AsyncClient, async_engine):
    await _seed(async_engine, [_scored_game(1, 9)])
    await _seed(async_engine, [
        _pool_giveaway("WLOW1", 50, 1, is_wishlist=True, entries=1000),
        _pool_giveaway("WHIG1", 40, 1, is_wishlist=True, entries=1),
    ])

    lens = (await test_client.get("/api/v1/giveaways/wishlist?lens=autojoin&min_chance=50")).json()["data"]

    assert [g["code"] for g in lens["giveaways"]] == ["WHIG1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path, item, code", [
    ("/api/v1/giveaways/wishlist", "wishlist", "WISH6"),
    ("/api/v1/giveaways/dlc", "dlc", "DLC06"),
])
async def test_type_tab_lens_reflects_the_exemption(test_client: AsyncClient, async_engine, path, item, code):
    await _seed_engine_pool(async_engine)
    await test_client.put("/api/v1/settings", json={"autojoin_min_score": 7, "autojoin_priorities": [{"type": item}]})

    lifted = (await test_client.get(f"{path}?lens=autojoin")).json()["data"]

    [candidate] = lifted["giveaways"]
    assert candidate["code"] == code
    assert candidate["decision"]["lifted_by"] == item
    assert candidate["decision"]["label"] == "Joinable"
    assert candidate["decision"]["detail"] == {"priority": item, "rank": 0, "lifted_by": item}

    await test_client.put("/api/v1/settings", json={"autojoin_priorities": []})
    obeying = (await test_client.get(f"{path}?lens=autojoin")).json()["data"]
    assert obeying["giveaways"] == [] and obeying["count"] == 0
    plain = (await test_client.get(path)).json()["data"]
    assert [g["code"] for g in plain["giveaways"]] == [code]


@pytest.mark.asyncio
async def test_lens_persists_nothing_and_fails_on_a_corrupt_list(test_client: AsyncClient, async_engine, no_outbound):
    await _seed_engine_pool(async_engine)
    await test_client.put("/api/v1/settings", json={"phpsessid": "secret-session"})
    settings_before = (await test_client.get("/api/v1/settings")).json()["data"]
    rows_before = await _stored_rows(async_engine)

    response = await test_client.get("/api/v1/giveaways/wishlist?lens=autojoin")

    assert response.status_code == 200
    assert "secret-session" not in response.text
    assert (await test_client.get("/api/v1/settings")).json()["data"] == settings_before
    assert await _stored_rows(async_engine) == rows_before
    await _corrupt_stored_priorities(async_engine)
    assert (await test_client.get("/api/v1/giveaways/wishlist?lens=autojoin")).status_code == 500
    assert no_outbound == []


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["excluded_genres", "included_genres"])
@pytest.mark.parametrize("path", ["/api/v1/giveaways/eligible", "/api/v1/giveaways/active?lens=autojoin"])
async def test_saved_policy_endpoints_refuse_a_corrupt_stored_genre_list(
    test_client: AsyncClient, async_engine, field, path
):
    """A genre column stored as a string would fold into single letters and let
    the excluded genre through; /eligible and the lens refuse it (CONFIG_002)."""
    await _seed_engine_pool(async_engine)
    await _corrupt_stored_column(async_engine, field, "Action")

    response = await test_client.get(path)

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "CONFIG_002"
    assert error["message"] == f"Genre list setting is invalid: {field} must be a list of strings"
    assert await _stored_eligibility(test_client, "GOOD9") == (None, None, None)


# ==================== QA: contract gaps (test engineer) ====================

SEVEN_POLICY_FIELDS = (
    "autojoin_min_price", "autojoin_min_score", "autojoin_min_reviews", "autojoin_max_game_age",
    "excluded_genres", "included_genres", "autojoin_priorities",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", SEVEN_POLICY_FIELDS)
async def test_preview_requires_each_of_the_seven_fields(test_client: AsyncClient, async_engine, missing):
    """Every policy field is required in the preview body, nullable ones included:
    a missing field is a 422, never a silent default from the saved row."""
    await _seed_engine_pool(async_engine)
    body = {k: v for k, v in _policy_body().items() if k != missing}

    response = await test_client.post("/api/v1/giveaways/preview", json=body)

    assert response.status_code == 422
    assert missing in response.text
    assert await _stored_eligibility(test_client, "GOOD9") == (None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["autojoin_min_price", "excluded_genres", "included_genres", "autojoin_priorities"])
async def test_preview_null_for_a_not_nullable_policy_field_is_422(test_client: AsyncClient, async_engine, field):
    """In PUT /settings a null priority list means 'unchanged'; a preview has no
    saved value to fall back on, so null for a non-nullable field is a 422."""
    await _seed_engine_pool(async_engine)

    response = await test_client.post("/api/v1/giveaways/preview", json=_policy_body(**{field: None}))

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [
    {"autojoin_min_price": -1},
    {"autojoin_min_reviews": -1},
    {"autojoin_max_game_age": 0},
    {"autojoin_min_score": -1},
    {"autojoin_priorities": "wishlist"},
    {"autojoin_priorities": [{"type": "ending_soon"}]},
    {"autojoin_priorities": [{"type": "wishlist", "threshold_minutes": 10}]},
    {"autojoin_priorities": [{"type": "bogus"}]},
    {"autojoin_priorities": [{"type": "ending_soon", "threshold_minutes": 10081}]},
    {"excluded_genres": [f"Genre {i}" for i in range(51)]},
    {"excluded_genres": "Action"},
    {"included_genres": [1]},
])
async def test_preview_rejects_what_put_settings_rejects(test_client: AsyncClient, async_engine, override):
    await _seed_engine_pool(async_engine)
    settings_before = (await test_client.get("/api/v1/settings")).json()["data"]

    response = await test_client.post("/api/v1/giveaways/preview", json=_policy_body(**override))

    assert response.status_code == 422
    assert (await test_client.get("/api/v1/settings")).json()["data"] == settings_before


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [5, 10080])
async def test_preview_accepts_the_threshold_bounds(test_client: AsyncClient, async_engine, value):
    await _seed_engine_pool(async_engine)

    response = await test_client.post(
        "/api/v1/giveaways/preview",
        json=_policy_body(autojoin_priorities=[{"type": "ending_soon", "threshold_minutes": value}]),
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_preview_counts_every_pool_row_by_code(test_client: AsyncClient, async_engine, no_outbound):
    """counts is the full per-code breakdown of the pool (active, not entered,
    hidden included), not just a sum that happens to match."""
    await _seed_engine_pool(async_engine)

    data = (await test_client.post("/api/v1/giveaways/preview", json=_policy_body())).json()["data"]

    assert data["pool"] == 8
    assert data["counts"] == {
        "eligible": 3, "score_below_min": 2, "price_below_min": 1, "hidden": 1, "no_game_data": 1,
    }
    assert data["count"] == data["counts"]["eligible"]


@pytest.mark.asyncio
async def test_preview_applies_the_bodys_genre_lists(test_client: AsyncClient, async_engine, no_outbound):
    """The body's include list decides (fail closed on the uncached game), and
    exclusion wins over inclusion; the saved lists are untouched."""
    await _seed(async_engine, [_scored_game(1, 9, ["RPG"]), _scored_game(2, 9, ["Action", "Indie"])])
    await _seed(async_engine, [
        _pool_giveaway("RPG01", 50, 1),
        _pool_giveaway("ACTN1", 40, 2),
        _pool_giveaway("UNCH1", 30, 999),
    ])
    body = _policy_body(autojoin_min_score=None, included_genres=["rpg", "Indie"], excluded_genres=["Action"])

    data = (await test_client.post("/api/v1/giveaways/preview", json=body)).json()["data"]

    assert [c["code"] for c in data["candidates"]] == ["RPG01"]
    assert data["counts"] == {"eligible": 1, "genre_excluded": 1, "genre_not_included": 1}
    settings = (await test_client.get("/api/v1/settings")).json()["data"]
    assert (settings["excluded_genres"], settings["included_genres"]) == ([], [])


@pytest.mark.asyncio
async def test_preview_on_an_empty_pool(test_client: AsyncClient, no_outbound):
    response = await test_client.post("/api/v1/giveaways/preview", json=_policy_body())

    assert response.status_code == 200
    assert response.json()["data"] == {
        "candidates": [], "count": 0, "pool": 0, "counts": {}, "budget_applied": False,
    }


@pytest.mark.asyncio
async def test_preview_candidates_carry_the_stored_last_cycle_decision(test_client: AsyncClient, async_engine):
    """eligibility_* on a candidate are what the last cycle stored; the live
    verdict is only in decision, and the stored row is not rewritten."""
    await _seed(async_engine, [_scored_game(1, 6)])
    row = _pool_giveaway("STALE", 50, 1)
    row.eligibility_reason = "score_below_min"
    row.eligibility_detail = {"score": 6, "min_score": 7}
    row.eligibility_checked_at = datetime(2026, 11, 1, 12, 0, 0)
    await _seed(async_engine, [row])

    data = (await test_client.post(
        "/api/v1/giveaways/preview", json=_policy_body(autojoin_min_score=3)
    )).json()["data"]

    [candidate] = data["candidates"]
    assert candidate["decision"]["code"] == "eligible"
    assert candidate["eligibility_reason"] == "score_below_min"
    assert candidate["eligibility_detail"] == {"score": 6, "min_score": 7}
    assert candidate["eligibility_label"] == "Review score 6 is below your minimum 7"
    assert candidate["eligibility_kind"] == "filter"
    assert candidate["eligibility_checked_at"] == "2026-11-01T12:00:00Z"
    assert (await _stored_rows(async_engine))["STALE"] == (
        "score_below_min", {"score": 6, "min_score": 7}, datetime(2026, 11, 1, 12, 0, 0))


@pytest.mark.asyncio
@pytest.mark.parametrize("method, path", [
    ("GET", "/api/v1/giveaways/registry"),
    ("GET", "/api/v1/giveaways/eligible"),
    ("POST", "/api/v1/giveaways/preview"),
    ("GET", "/api/v1/giveaways/active?lens=autojoin"),
    ("GET", "/api/v1/giveaways/wishlist?lens=autojoin"),
    ("GET", "/api/v1/giveaways/dlc?lens=autojoin"),
])
async def test_engine_endpoints_never_contact_steamgifts_with_a_session(
    test_client: AsyncClient, async_engine, no_outbound, method, path
):
    """With a session configured, no registry, preview or lens request starts a
    SteamGifts client (which would fetch the homepage for the XSRF token) or
    looks a game up on Steam, and the session never appears in the body."""
    await _seed_engine_pool(async_engine)
    await test_client.put("/api/v1/settings", json={"phpsessid": "secret-session", "xsrf_token": "secret-xsrf"})
    rows_before = await _stored_rows(async_engine)

    if method == "POST":
        response = await test_client.post(path, json=_policy_body())
    else:
        response = await test_client.get(path)

    assert response.status_code == 200
    assert no_outbound == []
    assert "secret-session" not in response.text and "secret-xsrf" not in response.text
    assert await _stored_rows(async_engine) == rows_before


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/giveaways/active", "/api/v1/giveaways/wishlist", "/api/v1/giveaways/dlc"])
async def test_lens_items_are_full_candidate_previews(test_client: AsyncClient, async_engine, path):
    await _seed_engine_pool(async_engine)
    await test_client.put("/api/v1/settings", json={
        "autojoin_min_score": None, "autojoin_priorities": [{"type": "wishlist"}, {"type": "dlc"}],
    })

    data = (await test_client.get(f"{path}?lens=autojoin")).json()["data"]

    assert set(data) == {"giveaways", "count", "lens", "budget_applied"}
    assert data["giveaways"]
    for item in data["giveaways"]:
        assert set(item) == GIVEAWAY_FIELDS | {"decision"}
        assert set(item["decision"]) == {"code", "label", "detail", "priority", "rank", "lifted_by"}
        assert item["decision"]["code"] == "eligible"


@pytest.mark.asyncio
@pytest.mark.parametrize("path, flag", [
    ("/api/v1/giveaways/wishlist", "is_wishlist"),
    ("/api/v1/giveaways/dlc", "is_dlc"),
])
async def test_type_tab_lens_leaves_out_entered_and_hidden_rows(test_client: AsyncClient, async_engine, path, flag):
    """The wishlist and DLC lens pools are not entered and not hidden, even for
    giveaways the priority list lifts over every filter."""
    await _seed(async_engine, [_scored_game(1, 9)])
    await _seed(async_engine, [
        _pool_giveaway("OPEN1", 50, 1, **{flag: True}),
        _pool_giveaway("ENTR1", 60, 1, is_entered=True, **{flag: True}),
        _pool_giveaway("HIDN1", 70, 1, is_hidden=True, **{flag: True}),
    ])
    await test_client.put("/api/v1/settings", json={"autojoin_priorities": [{"type": "wishlist"}, {"type": "dlc"}]})

    lens = (await test_client.get(f"{path}?lens=autojoin")).json()["data"]
    plain = (await test_client.get(path)).json()["data"]

    assert [g["code"] for g in lens["giveaways"]] == ["OPEN1"]
    assert lens["count"] == 1
    assert "ENTR1" in [g["code"] for g in plain["giveaways"]]  # the plain tab still lists it


@pytest.mark.asyncio
async def test_active_lens_intersects_min_score(test_client: AsyncClient, async_engine):
    """The browse min_score narrows the lens pool; the saved policy (no score
    minimum here) still decides inside it."""
    await _seed_engine_pool(async_engine)
    await test_client.put("/api/v1/settings", json={"autojoin_min_score": None, "autojoin_min_reviews": None})

    data = (await test_client.get("/api/v1/giveaways/active?lens=autojoin&min_score=8")).json()["data"]

    codes = [g["code"] for g in data["giveaways"]]
    assert codes == ["GOOD9", "GOOD2"]
    assert data["count"] == 2


@pytest.mark.asyncio
async def test_lens_offset_past_the_end_keeps_the_total(test_client: AsyncClient, async_engine):
    await _seed_engine_pool(async_engine)
    await test_client.put("/api/v1/settings", json={"autojoin_min_score": 7})

    data = (await test_client.get("/api/v1/giveaways/active?lens=autojoin&limit=5&offset=50")).json()["data"]

    assert data["giveaways"] == []
    assert data["count"] == 3


@pytest.mark.asyncio
async def test_lens_with_ending_within_on_the_dlc_tab(test_client: AsyncClient, async_engine):
    await _seed(async_engine, [_scored_game(1, 9)])
    await _seed(async_engine, [
        _pool_giveaway("DSOON", 50, 1, minutes=20, is_dlc=True),
        _pool_giveaway("DLATE", 60, 1, minutes=600, is_dlc=True),
    ])
    await test_client.put("/api/v1/settings", json={"autojoin_priorities": [{"type": "dlc"}]})

    data = (await test_client.get("/api/v1/giveaways/dlc?lens=autojoin&ending_within=30")).json()["data"]

    assert [g["code"] for g in data["giveaways"]] == ["DSOON"]
    assert data["count"] == 1


@pytest.mark.asyncio
async def test_browse_not_entered_paginates_and_ignores_policy_parameters(test_client: AsyncClient, async_engine):
    """min_score/min_price/min_reviews/max_price are no longer applied to the
    is_entered=false browse filter; limit/offset page through it."""
    await _seed_engine_pool(async_engine)

    full = [g["code"] for g in (await test_client.get("/api/v1/giveaways?is_entered=false")).json()["data"]["giveaways"]]
    page = (await test_client.get("/api/v1/giveaways?is_entered=false&limit=2&offset=2")).json()["data"]
    ignored = (await test_client.get(
        "/api/v1/giveaways?is_entered=false&min_score=9&min_price=60&min_reviews=100000&max_price=1"
    )).json()["data"]

    assert [g["code"] for g in page["giveaways"]] == full[2:4]
    assert [g["code"] for g in ignored["giveaways"]] == full
