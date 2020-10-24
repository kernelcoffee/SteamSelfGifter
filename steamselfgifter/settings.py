import argparse
import configparser
import logging
import pathlib

logger = logging.getLogger(__name__)
logging_format = "%(asctime)s %(levelname)s %(filename)s::%(funcName)s::%(lineno)d - %(message)s"


class Settings:
    __instance = None

    @staticmethod
    def getInstance():
        """ Static access method. """
        if Settings.__instance is None:
            Settings()
        return Settings.__instance

    def __init__(self):
        """ Virtually private constructor. """
        if Settings.__instance is not None:
            raise Exception("This class is a singleton!")
        else:
            Settings.__instance = self

        # Argument init
        config = configparser.ConfigParser()
        parser = argparse.ArgumentParser()
        parser.add_argument("-v", "--verbose", help="Increase verbosity of output", action="store_true")
        parser.add_argument("-d", "--debug", help="Enable debug mode", action="store_true")
        parser.add_argument("-c", "--config", help="Path of the config file", type=pathlib.Path)
        args = parser.parse_args()

        self.xsrf_token = ""
        self.points = 0

        # CONFIG FILE
        if args.config and not args.config.exists():
            raise Exception("Config file not found")

        config_path = args.config
        config.read(config_path)

        self.log_level = str(config["misc"]["logging"])

        self.session_id = str(config["network"]["PHPSESSID"])
        self.user_agent = str(config["network"]["user-agent"])

        self.upper_threshold = int(config["misc"]["upper_threshold"])
        self.lower_threshold = int(config["misc"]["lower_threshold"])
        self.game_min_price = int(config["game"]["min_price"])
        self.game_min_score = int(config["game"]["min_score"])
        self.game_min_reviews = int(config["game"]["min_reviews"])

        # VERBOSE
        if args.verbose or self.log_level == "INFO":
            logging.basicConfig(level=logging.INFO, format=logging_format)

        # DEBUG
        if args.debug or self.log_level == "DEBUG":
            logging.basicConfig(level=logging.DEBUG, format=logging_format)

        logger.info("Configuration complete...")

    @property
    def cookie(self):
        return {"PHPSESSID": self.session_id}

    @property
    def headers(self):
        return {"user-agent": self.user_agent}
