import logging
import requests
import settings
import datetime
import json
from network import get_page

logger = logging.getLogger(__name__)

class GiftGame:
    def __init__(self):
        self.name = ""
        self.price = 0
        self.url = ""
        self.steam_id = ""
        self.steam_game = None
        self.ref = ""
        self.is_trap = False
        self.entered = False
        self.time_left = 0

    def set_price(self, price):
        self.price = price
        last_div = None
        for last_div in self.price:
            pass
        if last_div:
            self.price = last_div.getText().replace("(", "").replace(")", "").replace("P", "")
        self.price = int(self.price)

    def set_url(self, url):
        self.url = url
        self.ref = self.url.split("/")[2]

    def set_steam_id(self, url):
        self.steam_id = url.split("/")[4]

    def get_age(self):
        date = datetime.strptime(self.steam_game.release_date, "%d %B, %Y")

    def enter(self):
        """enter to giveaway"""

        if not self.ref:
            logger.warning("Not reference for this game, cannot enter")
            return

        if settings.points < self.price:
            logger.info(f"Not enough money ({settings.points}), can't enter giveaway ({self.price})")
            return

        game_url = f"{settings.MAIN_URL}{self.url}"
        soup = get_page(game_url, check_safety=True)

        if not soup:
            self.is_trap = True
            return

        try:
            params = {
                "xsrf_token": settings.xsrf_token,
                "do": "entry_insert",
                "code": self.ref,
            }
            entry = requests.post(
                "https://www.steamgifts.com/ajax.php", data=params, cookies=settings.cookie, headers=settings.headers,
            )
            json_data = json.loads(entry.text)
            if json_data["type"] == "success":
                settings.points -= self.price
                logger.info(f"Giveaway entered for {self.name}, Coins left: {settings.points}")
                self.entered = True
        except Exception as e:
            logger.error(f"Error while entering giveaway: {str(e)}")
