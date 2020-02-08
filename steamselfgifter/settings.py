import logging
import configparser
import argparse
import pathlib
import os

logger = logging.getLogger(__name__)

config = configparser.ConfigParser()

MAIN_URL = "https://www.steamgifts.com"
WISHLIST_URL = "https://www.steamgifts.com/giveaways/search?"


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

    config_path = "config.ini"

    # VERBOSE
    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    # DEBUG
    if args.debug or os.environ.get("DEBUG"):
        logging.basicConfig(level=logging.DEBUG)

    # CONFIG PATH
    if args.config and args.config.exists():
        config_path = args.config

    config.read(config_path)

    cookie = {"PHPSESSID": dict(config._sections["cookies"])["phpsessid"]}
    headers = dict(config._sections["headers"])
