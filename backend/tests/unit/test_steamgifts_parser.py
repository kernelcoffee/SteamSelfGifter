"""Regression tests for utils.steamgifts_parser against a real captured page.

tests/fixtures/wishlist_page.html is a sanitized copy of a live
steamgifts.com/giveaways/search?type=wishlist page (captured 2026-07-18,
logged-in identity and XSRF tokens scrubbed). It contains:

- a pinned "Featured" ad section (div.pinned-giveaways) with 2 ad giveaways
- exactly one real wishlist giveaway: Tomb Raider IV-VI Remastered
  (code hVTVd, 30P)
- the nav bar with the user's points (400) and profile link (TestUser)

If SteamGifts changes their markup again, these tests fail loudly instead of
the bot silently scraping wrong data. Refresh the fixture with
tests/scripts/fetch_wishlist_page.py (scrub username/avatar/xsrf before
committing).
"""

from pathlib import Path

import pytest

from utils import steamgifts_parser as parser

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def wishlist_html() -> str:
    return (FIXTURES / "wishlist_page.html").read_text(encoding="utf-8")


class TestWishlistPageFixture:
    def test_ads_excluded_real_giveaway_kept(self, wishlist_html):
        giveaways = parser.parse_giveaway_list(wishlist_html, mark_wishlist=True)

        assert len(giveaways) == 1
        ga = giveaways[0]
        assert ga["code"] == "hVTVd"
        assert ga["game_name"] == "Tomb Raider IV-VI Remastered"
        assert ga["price"] == 30
        assert ga["is_wishlist"] is True
        assert ga["game_id"] == 2525380
        assert ga["end_time"] is not None
        # The links row is a div: "455 entries 2 comments" on this capture.
        assert ga["entries"] == 455

    def test_mark_wishlist_false(self, wishlist_html):
        giveaways = parser.parse_giveaway_list(wishlist_html, mark_wishlist=False)
        assert len(giveaways) == 1
        assert giveaways[0]["is_wishlist"] is False

    def test_pinned_ads_present_in_html(self, wishlist_html):
        # Guard against a silently outdated fixture: the ad section must
        # actually be there for the exclusion test above to mean anything.
        assert 'class="pinned-giveaways"' in wishlist_html
        assert wishlist_html.count('giveaway__row-inner-wrap') == 3  # 2 ads + 1 real

    def test_user_points(self, wishlist_html):
        assert parser.parse_user_points(wishlist_html) == 400

    def test_username(self, wishlist_html):
        assert parser.parse_username(wishlist_html) == "TestUser"

    def test_xsrf_token(self, wishlist_html):
        assert parser.extract_xsrf_token(wishlist_html) == "deadbeefdeadbeefdeadbeefdeadbeef"


class TestNoResultsMarker:
    def test_marker_present_on_empty_search_fixture(self):
        html = (FIXTURES / "empty_search_page.html").read_text(encoding="utf-8")
        assert parser.has_no_results_marker(html) is True
        assert parser.parse_giveaway_list(html) == []

    def test_marker_absent_on_populated_page(self, wishlist_html):
        assert parser.has_no_results_marker(wishlist_html) is False


class TestParserEdgeCases:
    def test_empty_page(self):
        assert parser.parse_giveaway_list("<html><body></body></html>") == []
        assert parser.parse_won_giveaways("<html><body></body></html>") == []
        assert parser.parse_entered_giveaways("<html><body></body></html>") == []
        assert parser.parse_user_points("<html><body></body></html>") is None
        assert parser.parse_username("<html><body></body></html>") is None
        assert parser.extract_xsrf_token("<html><body></body></html>") is None
        assert parser.parse_giveaway_game_id("<html><body></body></html>") is None

    def test_entries_with_thousands_separator(self):
        html = """
        <div class="giveaway__row-inner-wrap">
            <a href="/giveaway/AbCd1/x" class="giveaway__heading__name">Game</a>
            <span class="giveaway__heading__thin">(50P)</span>
            <div class="giveaway__links">
                <a href="/giveaway/AbCd1/x/entries"><span>1,234 entries</span></a>
                <a href="/giveaway/AbCd1/x/comments"><span>56 comments</span></a>
            </div>
        </div>
        """
        [ga] = parser.parse_giveaway_list(html)
        assert ga["entries"] == 1234

    def test_single_entry_singular(self):
        html = """
        <div class="giveaway__row-inner-wrap">
            <a href="/giveaway/AbCd1/x" class="giveaway__heading__name">Game</a>
            <div class="giveaway__links"><span>1 entry</span></div>
        </div>
        """
        [ga] = parser.parse_giveaway_list(html)
        assert ga["entries"] == 1

    def test_malformed_points_raises(self):
        html = '<span class="nav__points">no digits</span>'
        with pytest.raises(ValueError, match="Could not parse points"):
            parser.parse_user_points(html)

    def test_safety_check_pure(self):
        clean = parser.check_page_safety("a lovely giveaway, enjoy")
        assert clean["is_safe"] is True
        assert clean["safety_score"] == 100


@pytest.fixture(scope="module")
def comments_html() -> str:
    return (FIXTURES / "giveaway_page.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def description_html() -> str:
    return (FIXTURES / "giveaway_page_description.html").read_text(encoding="utf-8")


class TestGiveawayPageFixtures:
    """Structural regression tests against sanitized live giveaway pages.

    giveaway_page.html: a real giveaway with 6 visible comments (plus
    collapsed placeholders that must be excluded) and no description.
    giveaway_page_description.html: a real giveaway with a description
    and no comments. Refresh with tests/scripts/fetch_giveaway_page.py.
    """

    def test_comments_extracted_collapsed_excluded(self, comments_html):
        texts = parser.extract_giveaway_texts(comments_html)
        assert texts["description"] == ""
        assert len(texts["comments"]) == 6
        assert not any("collapsed" in c.lower() for c in texts["comments"])

    def test_fixture_actually_contains_collapsed_placeholders(self, comments_html):
        # Guard against a silently outdated fixture: the collapse-state blocks
        # must be present for the exclusion assertion above to mean anything.
        assert comments_html.count("comment__collapse-state") > 0

    def test_description_extracted(self, description_html):
        texts = parser.extract_giveaway_texts(description_html)
        assert texts["description"] == "Mystery Box Bundle - Holiday Edition, Fanatical"
        assert texts["comments"] == []

    def test_both_real_pages_score_safe(self, comments_html, description_html):
        assert parser.check_page_safety(comments_html)["verdict"] == "safe"
        assert parser.check_page_safety(description_html)["verdict"] == "safe"


class TestSafetyScoring:
    def test_trap_description_unsafe(self):
        result = parser.score_giveaway_safety(
            "Do not enter, this is a bot trap, you will get banned", []
        )
        assert result["verdict"] == "unsafe"
        assert result["is_safe"] is False
        assert result["safety_score"] < 50
        assert result["details"]

    def test_weak_word_borderline(self):
        result = parser.score_giveaway_safety("these screenshots look fake", [])
        assert result["verdict"] == "borderline"
        assert result["safety_score"] == 80

    def test_word_boundaries(self):
        result = parser.score_giveaway_safety(
            "urban banking robots and banners in abandoned bandit lands", []
        )
        assert result["verdict"] == "safe"
        assert result["safety_score"] == 100

    def test_comment_weight_capped(self):
        warnings = ["do not enter, bot trap"] * 10
        result = parser.score_giveaway_safety("", warnings)
        # Cap keeps a comment pile-on at borderline, never outright unsafe
        assert result["warning_comments"] == 10
        assert result["verdict"] == "borderline"
        assert result["safety_score"] == 60

    def test_single_warning_comment_safe(self):
        result = parser.score_giveaway_safety("", ["don't enter!!"])
        assert result["verdict"] == "safe"
        assert result["safety_score"] == 85

    def test_empty_texts_safe(self):
        result = parser.score_giveaway_safety("", [])
        assert result["verdict"] == "safe"
        assert result["safety_score"] == 100
        assert result["warning_comments"] == 0
