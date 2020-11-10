import logging
import re
import sys
import time

import requests
from bs4 import BeautifulSoup
from requests import RequestException
from settings import Settings

logger = logging.getLogger(__name__)
settings = Settings.getInstance()

forbidden_words = (" ban", " fake", " bot", " not enter", " don't enter")
good_words = (" bank", " banan", " both", " band", " banner", " bang")

MAIN_URL = "https://www.steamgifts.com"
WISHLIST_URL = "https://www.steamgifts.com/giveaways/search?"


def request_page(url):
    r = requests.get(url, cookies=settings.cookie, headers=settings.headers)
    if r.status_code != 200:
        return False
    return r


def _check_game_safety(request):
    # Some page are nefarious, let's see if there are warning signs
    bad_counter = good_counter = 0
    for bad_word in forbidden_words:
        bad_counter += len(re.findall(bad_word, request.text, flags=re.IGNORECASE))
    if bad_counter > 0:
        for good_word in good_words:
            good_counter += len(re.findall(good_word, request.text, flags=re.IGNORECASE))
        if bad_counter > good_counter:
            logger.warn(f"Safety validation failed: {request.url}")
            return False
    return True


def get_page(url, check_safety=False):
    try:
        r = requests.get(url=url, cookies=settings.cookie, headers=settings.headers)
    except RequestException as e:
        logger.warning(f"Cant connect to the site : {str(e)}")
        logger.warning("Waiting 2 minutes and reconnect...")
        time.sleep(120)
        return get_page(url)
    except TypeError as t:
        logger.error(f"Cant recognize your cookie value: {str(t)}.")
        sys.exit(0)

    if check_safety and not _check_game_safety(r):
        return False

    if r.status_code == 429:
        logger.error("Request limit rate hit, waiting 10 minutes before proceeding")
        time.sleep(600)
        return get_page(url)

    if r.status_code == 200:
        soup = BeautifulSoup(r.text, "html.parser")
        # Refresh data as soon as possible
        settings.xsrf_token = soup.find("input", {"name": "xsrf_token"})["value"]
        settings.points = int(soup.find("span", {"class": "nav__points"}).text)  # storage points
        return soup

    logger.error(f"Unsupported request status code {r.status_code}")
