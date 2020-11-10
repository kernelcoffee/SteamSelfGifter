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
    game = GiftGame()

    try:
        steam_game = steam.get_game(steam_id)
        game.game = steam_game
        game.name = steam_game.name

    except Exception as e:
        logger.error(f"{str(e)}")
        game.game = None

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


def get_games(filter_selection="All"):
    games = []
    index = 1
    url = f"{MAIN_URL}/giveaways/search?page="

    filter_url = {
        "All": "",
        "Wishlist": "&type=wishlist",
        "Recommended": "&type=recommended",
        "Copies": "&copy_min=2",
        "DLC": "&dlc=true",
        "New": "&type=new",
    }

    while True:
        try:
            page_url = f"{url}{index}{filter_url[filter_selection]}"
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

        if index > 3:
            logger.debug("Too many pages fetched, return game list early")
            return games

        for item in game_list:
            game = process_game(item)

            if not game.game:
                logger.info("Game {game.id} doesn't exist on steam, either trash or too old, let's hide it")
                game.hide()
                continue

            if not check_duplicate(game, games):
                games.append(game)


while True:
    # Process wishlist
    logger.info("Looking for games")
    entries = get_games("Wishlist")
    logger.info(f"Found {len(entries)}  to review")

    if settings.dlc_enabled:
        dlcs = get_games("DLC")
        entries += dlcs
        logger.info(f"Found {len(dlcs)} DLC to review")

    for entry in entries:
        if entry.price < settings.points:
            entry.enter()
            time.sleep(random.randint(8, 12))
        else:
            logger.info(f"Not enough points for {entry.game.type} {entry.name}, let's skip.")

    # We have a lot of points left, let's get more games
    if settings.autojoin_enabled and settings.points > settings.autojoin_start_at:
        time.sleep(random.randint(8, 12))
        logger.info("Looking for games to spend extra coins")
        games = get_games()
        logger.info(f"Found {len(games)} games to review")
        for game in games:
            if settings.points <= settings.autojoin_stop_at:
                logger.info("Not enough points left for automatically joining extra games.")
                break

            total_review_check = game.game.total_reviews >= settings.autojoin_min_reviews
            score_check = game.game.review_score >= settings.autojoin_min_score
            price_check = game.price >= settings.autojoin_min_price

            if total_review_check and score_check and price_check:
                game.enter()
                time.sleep(random.randint(8, 12))

    interval = random.randint(1000, 2000)
    logger.info(f"Waiting {round(interval/60)}m for next check - Current points : {settings.points}")
    time.sleep(interval)
