# Playmore / City Sports scraper
# Strategy: Playwright network intercept — discover underlying API, then replay directly
# Endpoints:
#   squash:   https://playmore.pl/reservation/21/courts?tagId=68
#   badminton: tagId TBD (discover during network intercept)

from .base import Slot


def scrape(sport: str = "squash") -> list[Slot]:
    # TODO: implement after discovery phase
    raise NotImplementedError
