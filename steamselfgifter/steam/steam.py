import logging
from datetime import datetime, timedelta

from steam.steamgame import SteamGame

logger = logging.getLogger(__name__)


class Steam:
    def __init__(self):
        self.game_library = dict()

    def get_game(self, steamId):
        if not self.game_library.get(steamId):
            self.game_library[steamId] = SteamGame(steamId)
            self.game_library[steamId].refresh()
            return self.game_library[steamId]

        game = self.game_library[steamId]
        if (datetime.utcnow() - game.modified_at) > timedelta(2):
            # Data is more than 2 days old
            try:
                game.refresh()
            except Exception as e:
                logger.error(f"Failed to refresh steam game : {str(e)}")
                return None
        return game
