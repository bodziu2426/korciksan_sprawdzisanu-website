"""
Hasta la Vista scraper — WordPress admin-ajax.php
---------------------------------------------------
Hasta uses a custom WordPress AJAX handler to return availability as HTML.
No authentication required for reading.

Availability endpoint:
  POST https://hastalavista.pl/wp-admin/admin-ajax.php
  body: operacja=ShowRezerwacjeTable&action=ShowRezerwacjeTable
        &data=YYYY-MM-DD&obiekt_typ=squash|badminton
        &godz_od=&godz_do=

Response: HTML with court grid (text/html)

Slot classes (discovered via hasta_calendar_dump.py):
  rez_wolne       — free (has <input> with data-godz_od, data-godz_do, data-obie_id)
  rez_zajete      — taken/booked
  rez_niedostepne — unavailable (outside opening hours)

Slots are 30-minute blocks.
Courts: up to 31 squash courts, 3+ badminton courts (non-sequential IDs).
"""

import re
from datetime import date, datetime, time, timedelta

import httpx
from bs4 import BeautifulSoup

from .base import Slot

AJAX_URL = "https://hastalavista.pl/wp-admin/admin-ajax.php"
VENUE = "hasta"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://hastalavista.pl/rezerwacje/",
    "X-Requested-With": "XMLHttpRequest",
}

SPORTS = ("squash", "badminton")


def _fetch_day_html(client: httpx.Client, sport: str, day: date) -> str:
    resp = client.post(
        AJAX_URL,
        data={
            "operacja": "ShowRezerwacjeTable",
            "action": "ShowRezerwacjeTable",
            "data": day.isoformat(),
            "obiekt_typ": sport,
            "godz_od": "",
            "godz_do": "",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.text


def _parse_price(text: str) -> float | None:
    """Parse '41,5 zł' → 41.5"""
    m = re.search(r"(\d+[.,]\d+|\d+)", text)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def _parse_time(text: str) -> time | None:
    m = re.match(r"(\d{1,2}):(\d{2})", text.strip())
    if m:
        return time(int(m.group(1)), int(m.group(2)))
    return None


def _parse_slots(html: str, sport: str, day: date) -> list[Slot]:
    soup = BeautifulSoup(html, "html.parser")
    now = datetime.now()
    slots: list[Slot] = []

    for court_div in soup.find_all("div", class_="court__body"):
        court_id = court_div.get("data-obie_id", "")

        # Court number from sibling header
        parent = court_div.parent
        header = parent.find("div", class_="court__hedaer")
        court_name = header.get_text(strip=True) if header else ""
        court_number = _extract_court_number(court_name)

        for wrapper in court_div.find_all("div", class_="court__item-wrapper"):
            # Time from court__hour (start time of this 30-min block)
            hour_div = wrapper.find("div", class_="court__hour")
            if not hour_div:
                continue
            start_time = _parse_time(hour_div.get_text(strip=True))
            if start_time is None:
                continue

            # Price from court__price
            price_div = wrapper.find("div", class_="court__price")
            price = _parse_price(price_div.get_text()) if price_div else None

            # Availability
            item = wrapper.find("div", class_="court__item")
            if item is None:
                continue

            classes = item.get("class", [])

            if "rez_wolne" in classes:
                # Free — get precise times from input data attributes
                inp = item.find("input")
                if inp:
                    start_time = _parse_time(inp.get("data-godz_od", "")) or start_time
                    court_id = inp.get("data-obie_id", court_id)
                    court_number = int(inp.get("data-court-number", court_number))
                is_available = True
            elif "rez_zajete" in classes:
                is_available = False
            elif "rez_niedostepne" in classes:
                is_available = False
            else:
                continue

            slots.append(Slot(
                venue=VENUE,
                sport=sport,
                court_id=court_id,
                court_number=court_number,
                date=day,
                start_time=start_time,
                duration_min=30,
                is_available=is_available,
                price=price,
                scraped_at=now,
            ))

    return slots


def _extract_court_number(name: str) -> int:
    """'Kort 13' → 13"""
    m = re.search(r"(\d+)", name)
    return int(m.group(1)) if m else 1


def scrape(sport: str = "squash", days_ahead: int = 7) -> list[Slot]:
    """
    Fetch court availability for Hasta la Vista.

    Args:
        sport:      "squash" or "badminton"
        days_ahead: how many days from today to fetch (default 7)

    Returns:
        List of Slot objects (available, taken, unavailable).
    """
    if sport not in SPORTS:
        raise ValueError(f"Unknown sport '{sport}'. Choose from: {SPORTS}")

    all_slots: list[Slot] = []

    with httpx.Client(follow_redirects=True, headers=HEADERS) as client:
        for offset in range(days_ahead):
            day = date.today() + timedelta(days=offset)
            html = _fetch_day_html(client, sport, day)
            all_slots.extend(_parse_slots(html, sport, day))

    return all_slots
