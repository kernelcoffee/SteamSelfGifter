import logging

from steam.steamgame import SteamGame
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

game_library = {}

class Steam:
    def get_game(self, steamId):
        if not game_library.get(steamId):
            game_library[steamId] = SteamGame(steamId)
            game_library[steamId].refresh()
            return game_library[steamId]

        game = game_library[steamId]
        if (datetime.utcnow() - game.modified_at) > timedelta(2):
            # Data is more than 2 days old
            try:
                game.refresh()
            except Exception as e:
                logger.error(f"Failed to refresh steam game : {str(e)}")
                return None
        return game
