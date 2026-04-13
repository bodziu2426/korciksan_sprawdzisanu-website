# WSC scraper
# Strategy: Playwright network intercept — discover underlying API, then replay directly
# Endpoint: https://wsclub.pl/rezerwacje

from .base import Slot


def scrape(sport: str = "squash") -> list[Slot]:
    # TODO: implement after discovery phase
    raise NotImplementedError
