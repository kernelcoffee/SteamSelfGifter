from steam.steamgame import SteamGame
from datetime import datetime, timedelta

game_library = {}

class Steam:
    def get_game(self, steamId):
        if not game_library.get(steamId):
            game_library[steamId] = SteamGame(steamId)
            return game_library[steamId]

        game = game_library[steamId]
        if (datetime.utcnow() - game.modified_at) > timedelta(2):
            # Data is more than 2 days old
            game.refresh()
        return game
