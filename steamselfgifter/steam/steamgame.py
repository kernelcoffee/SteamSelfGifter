import datetime
import logging
import requests

logger = logging.getLogger(__name__)


class SteamGame:
    def __init__(self, steamid):
        self.id = steamid
        self.modified_at = datetime.datetime.utcnow()
        self.is_bundle = False

    def _update_data(self):
        url = f"https://store.steampowered.com/api/appdetails?appids={self.id}&json=1"
        try:
            r = requests.get(url)
            data = r.json()
            if not data[self.id]["success"]:
                self.is_bundle = True
                raise TypeError("Giveaway is a bundle, let's skip")
            self.name = data[self.id]["data"]["name"]
            self.type = data[self.id]["data"]["type"]
            self.release_date = data[self.id]["data"]["release_date"]["date"]
        except Exception as e:
            raise Exception(f"Could not get steam game data: {str(e)} for {url}")

    def _update_review_data(self):
        data = ""
        try:
            r = requests.get(f"https://store.steampowered.com/appreviews/{self.id}?json=1")
            data = r.json()
            if not data["success"]:
                raise Exception("Giveaway is a bundle, let's skip")
            self.review_score = int(data["query_summary"]["review_score"])
            self.total_positive = int(data["query_summary"]["total_positive"])
            self.total_negative = int(data["query_summary"]["total_negative"])
            self.total_reviews = int(data["query_summary"]["total_reviews"])
        except Exception as e:
            raise Exception(f"Could not get steam score: {str(e)} for {r.url}")

    def refresh(self):
        self._update_data()
        self._update_review_data()
        self.modified_at = datetime.datetime.utcnow()
        logger.info(f"[SteamGame][Refresh] Done refreshing {self.name}")
