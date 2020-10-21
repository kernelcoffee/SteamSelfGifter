import logging
import os
import random
import time

from settings import Settings
from giftgame import GiftGame
from network import MAIN_URL, get_page
from steam.steam import Steam

logger = logging.getLogger(__name__)
random.seed(os.urandom)

steam = Steam()  # Steam Store game library
settings = Settings.getInstance()


def process_game(item):
    steam_id = item.find("a", {"class": "giveaway__icon"})["href"].split("/")[4]

    try:
        steam_game = steam.get_game(steam_id)
    except Exception as e:
        logger.error(f"{str(e)}")
        return None

    if steam_game.is_bundle:
        return None

    game = GiftGame()
    game.name = steam_game.name
    game.game = steam_game
    game.set_url(item.find("a", {"class": "giveaway__heading__name"})["href"])
    game.set_price(item.find_all("span", {"class": "giveaway__heading__thin"}))
    game.date_end = item.find("div", {"class": "giveaway__columns"}).find_all("span")[0]["data-timestamp"]

    return game


def check_duplicate(game, games):
    for item in games:
        if game.ref == item.ref:
            game.hide()
            games.remove(item)
            return True
    return False


def get_games(wishlist=False):
    games = []
    index = 1
    url = f"{MAIN_URL}/giveaways/search?page="
    end_url = "&type=wishlist" if wishlist else ""

    while True:
        try:
            page_url = f"{url}{index}{end_url}"
            soup = get_page(page_url)
            index += 1
            game_list = soup.find_all(
                lambda tag: tag.name == "div" and tag.get("class") == ["giveaway__row-inner-wrap"]
            )
        except Exception as e:
            logger.error(f"Failed to parse page {page_url}: {str(e)}")
            return games

        if not game_list:
            return games

        for item in game_list:
            game = process_game(item)
            if not game:
                continue
            if not check_duplicate(game, games):
                games.append(game)


while True:
    # Process wishlist
    games = get_games(wishlist=True)
    if games:
        logger.info(f"Found {len(games)} games in whishlist to review")

    for game in games:
        if game.price < settings.points:
            game.enter()
            time.sleep(random.randint(3, 7))
        else:
            logger.info(f"Not enough points for {game.name}, let's skip.")

    if settings.points > settings.upper_threshold:  # We have a lot of points left, let's get more games
        time.sleep(random.randint(2, 7))
        games = get_games()
        logger.info(f"Found {len(games)} games to review")
        for game in games:
            if settings.points <= settings.lower_threshold:
                logger.info("Not enough points left for non-wishlist games.")
                break

            total_review_check = game.game.total_reviews >= settings.game_min_reviews
            score_check = game.game.review_score >= settings.game_min_score
            price_check = game.price >= settings.game_min_price

            if total_review_check and score_check and price_check:
                game.enter()
                time.sleep(random.randint(3, 7))

    interval = random.randint(900, 1800)
    logger.info(f"Waiting {round(interval/60)}m for next check - Current points : {settings.points}")
    time.sleep(interval)
