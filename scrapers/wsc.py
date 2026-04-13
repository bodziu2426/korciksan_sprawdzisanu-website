"""
WSC Club scraper — reservise.com backend
-----------------------------------------
WSC uses reservise.com (Django) as its booking platform.

The calendar is fetched via Playwright (a real browser session is required —
direct httpx requests fail the Django session cookie check).

Calendar response: {"html": "<table>...</table>"}
Available slots:  <a class="free" data-begin="YYYY-MM-DD HH:MM:SS">
Taken/past slots: empty <td> (no <a> inside)

Resource IDs (discovered via wsc_discover.py):
  593 = squash   (duration: 3600s = 1h)
  873 = badminton (durations: 1800s / 3600s / 5400s / 7200s)
"""

import asyncio
from datetime import date, datetime, time, timedelta

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from .base import Slot

WSCLUB_URL = "https://wsclub.pl/rezerwacje"
CALENDAR_URL = "https://reservise.com/online/{resource_id}/calendar/"

RESOURCES = {
    "squash":    {"id": 593, "duration": 3600},
    "badminton": {"id": 873, "duration": 3600},
}

VENUE = "wsc"

MONTH_NAMES = {
    # Polish full
    "styczeń": 1, "luty": 2, "marzec": 3, "kwiecień": 4,
    "maj": 5, "czerwiec": 6, "lipiec": 7, "sierpień": 8,
    "wrzesień": 9, "październik": 10, "listopad": 11, "grudzień": 12,
    # Polish abbreviated
    "sty": 1, "lut": 2, "mar": 3, "kwi": 4,
    "cze": 6, "lip": 7, "sie": 8,
    "wrz": 9, "paź": 10, "lis": 11, "gru": 12,
    # English full
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    # English abbreviated
    "jan": 1, "feb": 2, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ── HTML parsing ─────────────────────────────────────────────────────────────

def _parse_header_dates(soup: BeautifulSoup) -> list[date | None]:
    """
    Extract ordered dates from <td class="day"> header cells.
    Format: '13 Kwi.' (day + Polish month abbreviation)
    Returns a list aligned with data columns (col 0 = first day column).
    """
    dates: list[date | None] = []
    for td in soup.select("thead td.day"):
        text = td.get_text(" ", strip=True)
        # Format: "Poniedziałek 13 Kwi."  (day-name  day-number  month-abbr)
        parts = text.split()
        if len(parts) < 3:
            dates.append(None)
            continue
        try:
            day = int(parts[1])
            month_key = parts[2].rstrip(".").lower()
            month = MONTH_NAMES.get(month_key)
            if month is None:
                dates.append(None)
                continue
            year = date.today().year
            # Handle year rollover (e.g. December → January)
            today = date.today()
            d = date(year, month, day)
            if d < today - timedelta(days=30):
                d = date(year + 1, month, day)
            dates.append(d)
        except (ValueError, IndexError):
            dates.append(None)
    return dates


def _parse_slots(html: str, sport: str, duration_sec: int) -> list[Slot]:
    soup = BeautifulSoup(html, "html.parser")
    now = datetime.now()
    slots: list[Slot] = []
    duration_min = duration_sec // 60
    court_id = f"wsc-{sport}"

    header_dates = _parse_header_dates(soup)

    for row in soup.select("tbody tr"):
        cells = row.find_all("td")
        if not cells:
            continue

        # First cell is the time label: <td class="time-inside">07:00</td>
        time_text = cells[0].get_text(strip=True)
        try:
            h, m = map(int, time_text.split(":"))
            slot_time = time(h, m)
        except (ValueError, AttributeError):
            continue

        # Remaining cells = one per day column
        for col_idx, cell in enumerate(cells[1:]):
            if col_idx >= len(header_dates):
                break

            link = cell.find("a", class_="free")
            if link and link.get("data-begin"):
                # Available slot — data-begin has the full datetime, no need for header date
                try:
                    dt = datetime.strptime(link["data-begin"], "%Y-%m-%d %H:%M:%S")
                    slot_time = dt.time()
                    cell_date = dt.date()
                except ValueError:
                    continue
                slots.append(Slot(
                    venue=VENUE,
                    sport=sport,
                    court_id=court_id,
                    court_number=1,
                    date=cell_date,
                    start_time=slot_time,
                    duration_min=duration_min,
                    is_available=True,
                    price=None,
                    scraped_at=now,
                ))
            else:
                # Empty cell = taken or in the past; need header date for this
                cell_date = header_dates[col_idx] if col_idx < len(header_dates) else None
                if cell_date is None:
                    continue
                slots.append(Slot(
                    venue=VENUE,
                    sport=sport,
                    court_id=court_id,
                    court_number=1,
                    date=cell_date,
                    start_time=slot_time,
                    duration_min=duration_min,
                    is_available=False,
                    price=None,
                    scraped_at=now,
                ))

    return slots


# ── Playwright calendar fetch ─────────────────────────────────────────────────

async def _fetch_calendars(sports: list[str]) -> dict[str, str]:
    """Open wsclub.pl in a headless browser and capture the calendar HTML for each sport."""
    needed = {RESOURCES[s]["id"]: s for s in sports}
    captured: dict[str, str] = {}  # sport -> html

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        async def handle_response(response):
            for resource_id, sport in needed.items():
                if (
                    f"/online/{resource_id}/calendar/" in response.url
                    and sport not in captured
                ):
                    try:
                        body = await response.json()
                        if "html" in body:
                            captured[sport] = body["html"]
                        else:
                            return
                    except Exception:
                        pass

        page.on("response", handle_response)
        await page.goto(WSCLUB_URL, timeout=30_000)

        # Wait up to 15 s for all required sports
        for _ in range(30):
            if set(captured) >= set(sports):
                break
            await asyncio.sleep(0.5)

        await browser.close()

    return captured


# ── Public API ────────────────────────────────────────────────────────────────

def scrape(sport: str = "squash") -> list[Slot]:
    """
    Fetch court availability for WSC.

    Args:
        sport: "squash" or "badminton"

    Returns:
        List of Slot objects (available and unavailable).
    """
    if sport not in RESOURCES:
        raise ValueError(f"Unknown sport '{sport}'. Choose from: {list(RESOURCES)}")

    html_by_sport = asyncio.run(_fetch_calendars([sport]))

    if sport not in html_by_sport:
        raise RuntimeError(f"Failed to capture calendar HTML for {sport}")

    resource = RESOURCES[sport]
    return _parse_slots(html_by_sport[sport], sport, resource["duration"])
