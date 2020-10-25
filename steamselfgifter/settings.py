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

        self.config_path = args.config
        config.read(self.config_path)

        self.log_level = config.get("misc", "logging", fallback="INFO")

        self.session_id = str(config["network"]["PHPSESSID"])
        self.user_agent = config.get(
            "network",
            "user-agent",
            fallback="Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:72.0) Gecko/20100101 Firefox/72.0",
        )

        self.dlc_enabled = config.getboolean("dlc", "enabled", fallback=False)

        self.autojoin_enabled = config.getboolean("autojoin", "enabled", fallback=False)
        self.autojoin_start_at = config.getint("autojoin", "start_at", fallback=350)
        self.autojoin_stop_at = config.getint("autojoin", "stop_at", fallback=200)
        self.autojoin_min_price = config.getint("autojoin", "min_price", fallback=10)
        self.autojoin_min_score = config.getint("autojoin", "min_score", fallback=7)
        self.autojoin_min_reviews = config.getint("autojoin", "min_reviews", fallback=1000)

        # VERBOSE
        if args.verbose or self.log_level == "INFO":
            logging.basicConfig(level=logging.INFO, format=logging_format)

        # DEBUG
        if args.debug or self.log_level == "DEBUG":
            logging.basicConfig(level=logging.DEBUG, format=logging_format)

        logger.info("Configuration complete...")
        self.save()

    def save(self):
        config = configparser.ConfigParser()

        config["network"] = {"PHPSESSID": self.session_id, "user-agent": self.user_agent}

        config["dlc"] = {"enabled": self.dlc_enabled}

        config["autojoin"] = {
            "enabled": self.autojoin_enabled,
            "start_at": self.autojoin_start_at,
            "stop_at": self.autojoin_stop_at,
            "min_price": self.autojoin_min_price,
            "min_score": self.autojoin_min_score,
            "min_reviews": self.autojoin_min_reviews,
        }

        config["misc"] = {"log_level": self.log_level}

        with open(self.config_path, "w") as configfile:
            config.write(configfile)

    @property
    def cookie(self):
        return {"PHPSESSID": self.session_id}

    @property
    def headers(self):
        return {"user-agent": self.user_agent}
