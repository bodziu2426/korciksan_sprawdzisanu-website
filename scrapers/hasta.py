# Hasta la Vista scraper
# Strategy: Login via Playwright, scrape HTML court table
# Endpoint: https://hastalavista.pl/rezerwacje/?type=squash|badminton

from .base import Slot


def scrape(sport: str = "squash") -> list[Slot]:
    # TODO: implement
    raise NotImplementedError
