import datetime
import logging
import requests

logger = logging.getLogger(__name__)


class SteamGame:
    def __init__(self, steamid):
        self.id = str(steamid)
        self.modified_at = datetime.datetime.utcnow()
        self.is_bundle = False

    def is_valid(self):
        property_list = [
            "name",
            "type",
            "release_date",
            "review_score",
            "total_positive",
            "total_negative",
            "total_reviews",
        ]

        if all(hasattr(self, attr) for attr in property_list):
            return True
        return False

    def _update_bundle(self):
        url = f"https://store.steampowered.com/api/packagedetails?packageids={self.id}&json=1"
        try:
            r = requests.get(url)
            r.raise_for_status()
            data = r.json()

            self.name = data[self.id]["data"]["name"]
            self.type = "bundle"
            self.bundle_content = []

            for app in data[self.id]["data"]["apps"]:
                item = SteamGame(app["id"])
                item.refresh()
                self.bundle_content.append(item)

            for item in self.bundle_content:
                if item.type == "game":
                    self.game_id = item.id
                    self.release_date = item.release_date
                    self.review_score = item.review_score
                    self.total_positive = item.total_positive
                    self.total_negative = item.total_negative
                    self.total_reviews = item.total_reviews
                    break
            if not hasattr(self, "game_id"):
                raise Exception("Not a game bundle")
        except Exception as e:
            raise Exception(f"Could not get Steam bundle data: {str(e)} for {url}")

    def _update_data(self):
        url = f"https://store.steampowered.com/api/appdetails?appids={self.id}&json=1"
        try:
            r = requests.get(url)
            r.raise_for_status()
            data = r.json()
            if not data[self.id]["success"]:
                self.is_bundle = True
                self._update_bundle()
                return
            data = data[self.id]["data"]
            self.name = data["name"]
            self.type = data["type"]
            self.release_date = data["release_date"]["date"]
        except Exception as e:
            raise Exception(f"Could not get steam game data: {str(e)} for {url}")

    def _update_review_data(self):
        if self.is_bundle:
            return False

        url = f"https://store.steampowered.com/appreviews/{self.id}?json=1"
        try:
            r = requests.get(url)
            r.raise_for_status()
            data = r.json()
            if not data["success"]:
                raise Exception("Giveaway is a bundle, let's skip")
            data = data["query_summary"]
            self.review_score = int(data["review_score"])
            self.total_positive = int(data["total_positive"])
            self.total_negative = int(data["total_negative"])
            self.total_reviews = int(data["total_reviews"])
        except Exception as e:
            raise Exception(f"Could not get steam score: {str(e)} for {url}")

    def refresh(self):
        if self.is_bundle:
            self._update_bundle()
        else:
            self._update_data()
            self._update_review_data()

        self.modified_at = datetime.datetime.utcnow()
        logger.info(f"[SteamGame][Refresh] Done refreshing {self.type} {self.name}")
