"""
Reservation recommendation engine
------------------------------------
Takes available slots + search params and returns ranked recommendations
for what to book and where.

Rules are venue-specific and condition-based (person count, sport, time).

Current rules:
  standard       — any venue, any person count: find free courts for requested sport
  playmore_dual  — Playmore only, persons >= 4: find hours where squash AND badminton
                   both have a free court (players can switch between adjacent courts)
"""

from dataclasses import dataclass
from datetime import date, time

from scrapers.base import Slot


@dataclass
class BookingSlot:
    """A single court to book as part of a recommendation."""
    venue: str
    sport: str
    court_id: str
    court_number: int
    start_time: time
    duration_min: int
    price: float | None


@dataclass
class Recommendation:
    """One actionable booking suggestion."""
    venue: str
    label: str
    rule: str               # which rule produced this
    hour: time              # primary start time
    bookings: list[BookingSlot]
    score: float            # higher = better (for sorting)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _group_by_hour(slots: list[Slot]) -> dict[time, list[Slot]]:
    """Group available slots by start_time."""
    groups: dict[time, list[Slot]] = {}
    for s in slots:
        groups.setdefault(s.start_time, []).append(s)
    return groups


def _slots_to_bookings(slots: list[Slot]) -> list[BookingSlot]:
    return [
        BookingSlot(
            venue=s.venue,
            sport=s.sport,
            court_id=s.court_id,
            court_number=s.court_number,
            start_time=s.start_time,
            duration_min=s.duration_min,
            price=s.price,
        )
        for s in slots
    ]


# ── Rules ─────────────────────────────────────────────────────────────────────

def _rule_standard(
    slots_by_sport: dict[str, list[Slot]],
    venue: str,
    requested_sport: str,
) -> list[Recommendation]:
    """
    Standard rule: for each hour that has at least one free court of the
    requested sport, produce one recommendation (pick the first free court).
    """
    sport_slots = [
        s for s in slots_by_sport.get(requested_sport, [])
        if s.venue == venue
    ]
    recommendations = []
    for hour, hour_slots in _group_by_hour(sport_slots).items():
        court = hour_slots[0]
        recommendations.append(Recommendation(
            venue=venue,
            label=f"{requested_sport.capitalize()} at {_venue_display(venue)} - kort {court.court_number}",
            rule="standard",
            hour=hour,
            bookings=_slots_to_bookings([court]),
            score=1.0,
        ))
    return recommendations


def _rule_playmore_dual(
    slots_by_sport: dict[str, list[Slot]],
    persons: int,
) -> list[Recommendation]:
    """
    Playmore dual-sport rule (persons >= 4):
    Find hours where both a squash court AND a badminton court are free.
    Suggest booking both so 4 players can switch between sports.

    Playmore courts are physically adjacent — this only makes sense at Playmore.
    """
    if persons < 4:
        return []

    squash_slots = [s for s in slots_by_sport.get("squash", []) if s.venue == "playmore"]
    badminton_slots = [s for s in slots_by_sport.get("badminton", []) if s.venue == "playmore"]

    squash_by_hour = _group_by_hour(squash_slots)
    badminton_by_hour = _group_by_hour(badminton_slots)

    shared_hours = set(squash_by_hour) & set(badminton_by_hour)

    recommendations = []
    for hour in sorted(shared_hours):
        sq = squash_by_hour[hour][0]
        bd = badminton_by_hour[hour][0]
        recommendations.append(Recommendation(
            venue="playmore",
            label=f"Squash + Badminton at Playmore ({persons} osób, zmiana kortów)",
            rule="playmore_dual",
            hour=hour,
            bookings=_slots_to_bookings([sq, bd]),
            score=2.0,  # ranked above standard single-sport
        ))
    return recommendations


def _venue_display(venue: str) -> str:
    return {"playmore": "Playmore", "wsc": "WSC", "hasta": "Hasta la Vista"}.get(venue, venue)


# ── Public API ────────────────────────────────────────────────────────────────

def recommend(
    available_slots: list[Slot],
    sport: str,
    persons: int = 2,
    time_from: time | None = None,
    time_to: time | None = None,
) -> list[Recommendation]:
    """
    Generate ranked booking recommendations from a list of available slots.

    Args:
        available_slots: all available slots (across all venues) for a given date
        sport:           requested sport ("squash" or "badminton")
        persons:         number of players (affects which rules apply)
        time_from:       earliest acceptable start time (inclusive)
        time_to:         latest acceptable start time (inclusive)

    Returns:
        Recommendations sorted by hour then score (descending).
    """
    # Filter by time window
    def in_window(s: Slot) -> bool:
        if time_from and s.start_time < time_from:
            return False
        if time_to and s.start_time > time_to:
            return False
        return True

    slots = [s for s in available_slots if in_window(s)]

    # Group by sport for rule evaluation
    slots_by_sport: dict[str, list[Slot]] = {}
    for s in slots:
        slots_by_sport.setdefault(s.sport, []).append(s)

    all_recommendations: list[Recommendation] = []
    venues = {s.venue for s in slots}

    # Apply standard rule for each venue
    for venue in venues:
        all_recommendations.extend(_rule_standard(slots_by_sport, venue, sport))

    # Apply Playmore dual-sport rule
    all_recommendations.extend(_rule_playmore_dual(slots_by_sport, persons))

    # Sort: by hour asc, then score desc
    all_recommendations.sort(key=lambda r: (r.hour, -r.score))

    return all_recommendations
