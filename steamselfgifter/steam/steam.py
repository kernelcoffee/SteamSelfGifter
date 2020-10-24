import logging
from datetime import datetime, timedelta
import time

from steam.steamgame import SteamGame

logger = logging.getLogger(__name__)


class Steam:
    def __init__(self):
        self.game_library = dict()

    def get_game(self, steamId):
        if not self.game_library.get(steamId):
            self.game_library[steamId] = SteamGame(steamId)
            self.game_library[steamId].refresh()
            # Slow down request to avoid data rate
            time.sleep(1)
            return self.game_library[steamId]

        game = self.game_library[steamId]
        if (datetime.utcnow() - game.modified_at) > timedelta(2):
            # Data is more than 2 days old
            logger.info("SteamGame data is old, updating...")
            game.refresh()
        return game
