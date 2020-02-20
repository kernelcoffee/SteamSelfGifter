import logging
import configparser
import argparse
import pathlib
import os
import random

logger = logging.getLogger(__name__)
logging_format="%(asctime)s %(levelname)s %(filename)s::%(funcName)s::%(lineno)d - %(message)s"

config = configparser.ConfigParser()

MAIN_URL = "https://www.steamgifts.com"
WISHLIST_URL = "https://www.steamgifts.com/giveaways/search?"


def init():
    global cookie
    global headers
    global xsrf_token
    global points
    global upper_threshold
    global lower_threshold
    global game_min_price
    global game_min_score
    global game_min_reviews

    xsrf_token = ""
    points = 0

    # Init options
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="Increase verbosity of output", action="store_true")
    parser.add_argument("-d", "--debug", help="Enable debug mode", action="store_true")
    parser.add_argument("-c", "--config", help="Path of the config file", type=pathlib.Path)
    args = parser.parse_args()

    # CONFIG FILE
    if args.config and args.config.exists():
        config_path = args.config
        config.read(config_path)
        session_id = config["cookies"]["PHPSESSID"]
        log_level = config["misc"]["logging"]
        upper_threshold = int(config["misc"]["upper_threshold"])
        lower_threshold = int(config["misc"]["lower_threshold"])
        game_min_price = int(config["game"]["min_price"])
        game_min_score = int(config["game"]["min_score"])
        game_min_reviews = int(config["game"]["min_reviews"])
    else:
        session_id = os.environ.get("PHPSESSID")
        log_level = os.environ.get("LOGGING")
        upper_threshold = 350
        lower_threshold = 200
        game_min_price = 10
        game_min_score = 7
        game_min_reviews = 500


    # VERBOSE
    if args.verbose or log_level == "INFO":
        logging.basicConfig(level=logging.INFO, format=logging_format)

    # DEBUG
    if args.debug or log_level == "DEBUG":
        logging.basicConfig(level=logging.DEBUG, format=logging_format)

    user_agent = "Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:72.0) Gecko/20100101 Firefox/72.0"

    cookie = {"PHPSESSID": session_id}
    headers = {"user-agent": user_agent}
    logger.info("Configuration complete...")
