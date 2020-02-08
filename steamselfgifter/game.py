import logging
import requests
import settings
import json
from network import get_page

logger = logging.getLogger(__name__)


class Game:
    def __init__(self, name, price, url):
        self.name = name
        self.price = int(price)
        self.url = url
        self.ref = self.url.split("/")[2]
        self.is_trap = False
        self.entered = False

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

        self.name = soup.title.string

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

