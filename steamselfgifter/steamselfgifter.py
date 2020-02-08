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

    end_url = ""
    if wishlist:
        end_url = "&type=wishlist"

    while True:
        soup = get_page(f"{url}{index}{end_url}")
        try:
            gifts_list = soup.find_all(
                lambda tag: tag.name == "div" and tag.get("class") == ["giveaway__row-inner-wrap"]
            )

            if not gifts_list:
                return games

            for item in gifts_list:
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
    logger.info(f"Found {len(games)} games in whislist")
    logger.info(f"{settings.points} coins available")
    for game in games:
        if game.price < settings.points:
            game.enter()
            time.sleep(random.randint(3, 7))
    time.sleep(900)
