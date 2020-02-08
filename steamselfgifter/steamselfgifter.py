import logging
import sys
import os
import time
import random
from bs4 import BeautifulSoup

from game import Game
from network import get_page
import settings

logger = logging.getLogger(__name__)
random.seed(os.urandom)


def get_games(wishlist=False):
    games = []
    index = 1
    url = f"{settings.MAIN_URL}/giveaways/search?page="
    end_url = "&type=wishlist" if wishlist else ""

    while True:
        soup = get_page(f"{url}{index}{end_url}")
        try:
            game_list = soup.find_all(
                lambda tag: tag.name == "div" and tag.get("class") == ["giveaway__row-inner-wrap"]
            )

            if not game_list:
                return games

            for item in game_list:
                game_price = item.find_all("span", {"class": "giveaway__heading__thin"})
                last_div = None
                for last_div in game_price:
                    pass
                if last_div:
                    price = last_div.getText().replace("(", "").replace(")", "").replace("P", "")
                game_name = item.find("a", {"class": "giveaway__heading__name"}).text.encode("utf-8")
                game_url = item.find("a", {"class": "giveaway__heading__name"})["href"]
                games.append(Game(game_name, price, game_url))
            index += 1
            time.sleep(random.randint(3, 7))
        except Exception as e:
            logger.error(e)


settings.init()
while True:
    games = get_games(wishlist=True)
    for game in games:
        if game.price < settings.points:
            game.enter()
            time.sleep(random.randint(3, 7))
        else:
            logger.info(f"Not enough points for {game.name}, let's skip.")
    if games: # Log result
        logger.info(f"{len(games)} games have been processed")
        logger.info(f"Price\tName")
        for game in games:
            logger.info(f"{game.price}\t{game.name}")

    interval = random.randint(900, 1800)
    logger.info(f"Waiting {round(interval/60)}m for next check")
    time.sleep(interval)
