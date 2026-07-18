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


class TestParserEdgeCases:
    def test_empty_page(self):
        assert parser.parse_giveaway_list("<html><body></body></html>") == []
        assert parser.parse_won_giveaways("<html><body></body></html>") == []
        assert parser.parse_entered_giveaways("<html><body></body></html>") == []
        assert parser.parse_user_points("<html><body></body></html>") is None
        assert parser.parse_username("<html><body></body></html>") is None
        assert parser.extract_xsrf_token("<html><body></body></html>") is None
        assert parser.parse_giveaway_game_id("<html><body></body></html>") is None

    def test_malformed_points_raises(self):
        html = '<span class="nav__points">no digits</span>'
        with pytest.raises(ValueError, match="Could not parse points"):
            parser.parse_user_points(html)

    def test_safety_check_pure(self):
        clean = parser.check_page_safety("a lovely giveaway, enjoy")
        assert clean["is_safe"] is True
        assert clean["safety_score"] == 100

        trap = parser.check_page_safety(
            "please do not enter this is fake and you will get a ban, bot trap"
        )
        assert trap["is_safe"] is False
