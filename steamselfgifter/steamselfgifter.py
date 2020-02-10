import logging
import sys
import os
import time
import random
from bs4 import BeautifulSoup

from giftgame import GiftGame
from steam.steam import Steam
from network import get_page
import settings

logger = logging.getLogger(__name__)
random.seed(os.urandom)

steam = Steam()  # Steam Store game library


def get_games(wishlist=False):
    games = []
    index = 1
    url = f"{settings.MAIN_URL}/giveaways/search?page="
    end_url = "&type=wishlist" if wishlist else ""

    while True:
        soup = get_page(f"{url}{index}{end_url}")
        try:
            index += 1
            game_list = soup.find_all(
                lambda tag: tag.name == "div" and tag.get("class") == ["giveaway__row-inner-wrap"]
            )

            if not game_list:
                return games

            for item in game_list:
                game = GiftGame()
                game.set_steam_id(item.find("a", {"class": "giveaway__icon"})["href"])
                game.set_price(item.find_all("span", {"class": "giveaway__heading__thin"}))
                game.set_url(item.find("a", {"class": "giveaway__heading__name"})["href"])
                games.append(game)
        except Exception as e:
            logger.error(f"Error while parsing the game list:{str(e)}")


def print_result(games):
    if not games:  # Log result
        return

    logger.info(f"{len(games)} games have been processed")
    logger.info(f"Price\tScore\tName")
    for game in games:
        logger.info(game.print())


settings.init()

while True:
    # Process wishlist
    games = get_games(wishlist=True)
    for game in games:
        if game.price < settings.points:
            game.enter()
            time.sleep(random.randint(3, 7))
        else:
            logger.info(f"Not enough points for {game.name}, let's skip.")

    if settings.points > settings.upper_threshold:  # We have a lot of points left, let's get more games
        time.sleep(random.randint(2, 7))
        games = get_games()
        for game in games:
            if settings.points <= settings.lower_threshold:
                logger.info("Not enough points left for non-wishlist games.")
                break

            total_review_check = game.steam_game.total_reviews >= settings.game_min_reviews
            score_check = game.steam_game.review_score >= settings.game_min_score
            price_check = game.price >= settings.game_min_price

            if total_review_check and score_check and price_check:
                game.enter()
                time.sleep(random.randint(3, 7))

    interval = random.randint(900, 1800)
    logger.info(f"Waiting {round(interval/60)}m for next check")
    time.sleep(interval)
