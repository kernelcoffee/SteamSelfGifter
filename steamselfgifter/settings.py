import logging
import configparser
import argparse
import pathlib
import os
import random

logger = logging.getLogger(__name__)

config = configparser.ConfigParser()

MAIN_URL = "https://www.steamgifts.com"
WISHLIST_URL = "https://www.steamgifts.com/giveaways/search?"

upper_threshold = 350
lower_threshold = 200
game_min_price = 10
game_min_score = 7
game_min_reviews = 100
game_max_age = "5y"

def init():
    global cookie
    global headers
    global xsrf_token
    global points

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
        log_level = config["misc"]["logging"]
        session_id = config["cookies"]["PHPSESSID"]
    else:
        log_level = os.environ.get("LOGGING")
        session_id = os.environ.get("PHPSESSID")

    # VERBOSE
    if args.verbose or log_level == "INFO":
        logging.basicConfig(level=logging.INFO)

    # DEBUG
    if args.debug or log_level == "DEBUG":
        logging.basicConfig(level=logging.DEBUG)

    user_agent = "Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:72.0) Gecko/20100101 Firefox/72.0"

    cookie = {"PHPSESSID": session_id}
    headers = {"user-agent": user_agent}
