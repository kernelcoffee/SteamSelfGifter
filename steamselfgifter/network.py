import logging
import requests
import sys
import time
import re
from requests import RequestException

from bs4 import BeautifulSoup

import settings

logger = logging.getLogger(__name__)

forbidden_words = (" ban", " fake", " bot", " not enter", " don't enter")
good_words = (" bank", " banan", " both", " band", " banner", " bang")


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
            logger.warn(f"Safety validation failed: {r.url}")
            return False
    return True


def get_page(url=settings.MAIN_URL, check_safety=False):
    try:
        r = requests.get(url, cookies=settings.cookie, headers=settings.headers)

        if not _check_game_safety(r):
            return False

        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            # Refresh data as soon as possible
            settings.xsrf_token = soup.find("input", {"name": "xsrf_token"})["value"]
            settings.points = int(soup.find("span", {"class": "nav__points"}).text)  # storage points
            return soup
    except RequestException as e:
        logger.warning("Cant connect to the site")
        logger.warning("Waiting 2 minutes and reconnect...")
        time.sleep(120)
        get_page()
    except TypeError:
        logger.error("Cant recognize your cookie value.")
        sys.exit(0)
