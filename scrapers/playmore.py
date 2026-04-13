"""
Playmore / City Sports scraper — zephyr.playmore.pl API
---------------------------------------------------------
Playmore uses a clean REST API — no HTML parsing, no browser session needed.

Availability endpoint (no auth required):
  GET https://zephyr.playmore.pl/api:4Tf8JTHd/venue/get_object_availabilities/21
      ?tag_id={tag_id}&date={YYYY-MM-DD}

Response: list of courts, each with available start times as minutes from midnight.
  e.g. 480 = 08:00, 540 = 09:00, 570 = 09:30

Venue: 21 = City Sports 4 People, Wrocław
Tags (discovered via playmore_discover.py):
  68 = Squash   (courts: 175, 176, 177 — durations: 60, 120 min)
  69 = Badminton (courts: 178, 179, 180 — durations: 60, 90, 120 min)
"""

from datetime import date, datetime, time, timedelta

import httpx

from .base import Slot

BASE_URL = "https://zephyr.playmore.pl/api:4Tf8JTHd"
VENUE_ID = 21

TAGS = {
    "squash":    {"tag_id": 68, "default_duration": 60},
    "badminton": {"tag_id": 69, "default_duration": 60},
}

VENUE = "playmore"


def _minutes_to_time(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def _fetch_day(
    client: httpx.Client,
    tag_id: int,
    day: date,
) -> list[dict]:
    resp = client.get(
        f"{BASE_URL}/venue/get_object_availabilities/{VENUE_ID}",
        params={"tag_id": tag_id, "date": day.isoformat()},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _parse_day(
    courts: list[dict],
    sport: str,
    day: date,
    duration_min: int,
) -> list[Slot]:
    now = datetime.now()
    slots: list[Slot] = []
    duration_key = str(duration_min)

    for court in courts:
        court_id = str(court["venue_sport_object_id"])
        court_name = court["venue_sport_object_name"]  # e.g. "Squash nr. 1"
        court_number = _court_number(court_name)
        availability = court.get("venue_sport_object_availability", {})
        available_starts = set(availability.get(duration_key, []))

        # Build the full set of possible slots for this day from opening hours.
        # We use all start times across any duration as the universe of possible slots.
        all_starts: set[int] = set()
        for starts in availability.values():
            all_starts.update(starts)

        for start_min in sorted(all_starts):
            slots.append(Slot(
                venue=VENUE,
                sport=sport,
                court_id=court_id,
                court_number=court_number,
                date=day,
                start_time=_minutes_to_time(start_min),
                duration_min=duration_min,
                is_available=start_min in available_starts,
                price=None,
                scraped_at=now,
            ))

    return slots


def _court_number(name: str) -> int:
    """Extract court number from name like 'Squash nr. 1' → 1."""
    parts = name.rsplit(" ", 1)
    try:
        return int(parts[-1])
    except ValueError:
        return 1


def scrape(sport: str = "squash", days_ahead: int = 7) -> list[Slot]:
    """
    Fetch court availability for Playmore / City Sports.

    Args:
        sport:      "squash" or "badminton"
        days_ahead: how many days from today to fetch (default 7)

    Returns:
        List of Slot objects for each court × day × timeslot.
    """
    if sport not in TAGS:
        raise ValueError(f"Unknown sport '{sport}'. Choose from: {list(TAGS)}")

    tag = TAGS[sport]
    tag_id = tag["tag_id"]
    duration_min = tag["default_duration"]

    all_slots: list[Slot] = []

    with httpx.Client(follow_redirects=True) as client:
        for offset in range(days_ahead):
            day = date.today() + timedelta(days=offset)
            courts = _fetch_day(client, tag_id, day)
            all_slots.extend(_parse_day(courts, sport, day, duration_min))

    return all_slots
