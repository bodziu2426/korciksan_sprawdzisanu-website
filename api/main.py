"""
Korciksan Sprawdzisanu — FastAPI backend
------------------------------------------
Endpoints:
  GET  /search               — main recommendation search
  GET  /venues               — cache status for all venue+sport combos
  POST /refresh/{venue}/{sport} — force re-scrape a venue+sport

Run with:
  uvicorn api.main:app --reload
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from typing import Annotated

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.models import (
    BookingSlotOut,
    RecommendationOut,
    RefreshResponse,
    SearchResponse,
    VenueStatus,
)
from rules.engine import BookingSlot, Recommendation, recommend
from scrapers.base import Slot
from storage.db import (
    get_slots,
    init_db,
    is_cache_fresh,
    last_scraped,
    upsert_slots,
)

app = FastAPI(title="Korciksan Sprawdzisanu", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread pool for running sync scrapers without blocking the event loop
_executor = ThreadPoolExecutor(max_workers=3)

# Venue+sport combos we track
VENUE_SPORTS = [
    ("playmore", "squash"),
    ("playmore", "badminton"),
    ("wsc",      "squash"),
    ("wsc",      "badminton"),
    ("hasta",    "squash"),
    ("hasta",    "badminton"),
]


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    init_db()


# ── Scraper helpers ───────────────────────────────────────────────────────────

def _run_scraper(venue: str, sport: str) -> list[Slot]:
    """Run the appropriate scraper synchronously (called in thread pool)."""
    if venue == "playmore":
        from scrapers.playmore import scrape
        return scrape(sport)
    elif venue == "wsc":
        from scrapers.wsc import scrape
        return scrape(sport)
    elif venue == "hasta":
        from scrapers.hasta import scrape
        return scrape(sport)
    raise ValueError(f"Unknown venue: {venue}")


async def _refresh_if_stale(venue: str, sport: str) -> str:
    """
    Check cache freshness; scrape and store if stale.
    Returns "fresh", "refreshed", or "failed".
    """
    if is_cache_fresh(venue, sport):
        return "fresh"
    try:
        loop = asyncio.get_event_loop()
        slots = await loop.run_in_executor(_executor, _run_scraper, venue, sport)
        upsert_slots(slots)
        return "refreshed"
    except Exception as e:
        print(f"[refresh] {venue}/{sport} failed: {e}")
        return "failed"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/search", response_model=SearchResponse)
async def search(
    sport:     Annotated[str,  Query(description="squash or badminton")] = "squash",
    date:      Annotated[str,  Query(description="YYYY-MM-DD, defaults to today")] = "",
    persons:   Annotated[int,  Query(description="Number of players", ge=1, le=10)] = 2,
    time_from: Annotated[str,  Query(description="Earliest start HH:MM")] = "",
    time_to:   Annotated[str,  Query(description="Latest start HH:MM")] = "",
    venues:    Annotated[str,  Query(description="Comma-separated venues to include")] = "",
):
    if sport not in ("squash", "badminton"):
        raise HTTPException(400, "sport must be 'squash' or 'badminton'")

    # Parse date
    search_date = _parse_date(date)

    # Parse optional times
    tf = _parse_time(time_from) if time_from else None
    tt = _parse_time(time_to)   if time_to   else None

    # Parse venue filter
    venue_filter = [v.strip() for v in venues.split(",") if v.strip()] or None

    # Determine which venue+sport combos to refresh
    # For dual-sport rule (persons >= 4 at Playmore) we also need badminton slots
    sports_needed = {sport}
    if persons >= 4:
        sports_needed.add("badminton")
        sports_needed.add("squash")

    combos = [
        (v, sp) for v, sp in VENUE_SPORTS
        if sp in sports_needed
        and (venue_filter is None or v in venue_filter)
    ]

    # Refresh stale caches concurrently
    refresh_tasks = [_refresh_if_stale(v, sp) for v, sp in combos]
    refresh_results = await asyncio.gather(*refresh_tasks)
    cache_info = {f"{v}/{sp}": r for (v, sp), r in zip(combos, refresh_results)}

    # Query DB for available slots on requested date
    active_venues = venue_filter or [v for v, _ in VENUE_SPORTS]
    all_slots: list[Slot] = []
    for sp in sports_needed:
        all_slots.extend(
            get_slots(
                sport=sp,
                date_from=search_date.isoformat(),
                date_to=search_date.isoformat(),
                available_only=True,
                venues=active_venues,
            )
        )

    # Generate recommendations
    recs = recommend(all_slots, sport=sport, persons=persons, time_from=tf, time_to=tt)

    return SearchResponse(
        date=search_date,
        sport=sport,
        persons=persons,
        time_from=tf,
        time_to=tt,
        recommendations=[_rec_out(r) for r in recs],
        cache_info=cache_info,
    )


@app.get("/venues", response_model=list[VenueStatus])
def venues_status():
    return [
        VenueStatus(
            venue=v,
            sport=sp,
            cache_fresh=is_cache_fresh(v, sp),
            last_scraped=_dt_str(last_scraped(v, sp)),
        )
        for v, sp in VENUE_SPORTS
    ]


@app.post("/refresh/{venue}/{sport}", response_model=RefreshResponse)
async def refresh_venue(venue: str, sport: str):
    valid_venues = {v for v, _ in VENUE_SPORTS}
    if venue not in valid_venues:
        raise HTTPException(400, f"Unknown venue '{venue}'")
    if sport not in ("squash", "badminton"):
        raise HTTPException(400, "sport must be 'squash' or 'badminton'")

    try:
        loop = asyncio.get_event_loop()
        slots = await loop.run_in_executor(_executor, _run_scraper, venue, sport)
        upsert_slots(slots)
        return RefreshResponse(venue=venue, sport=sport, slots_stored=len(slots), status="ok")
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(s: str) -> date:
    if not s:
        return date.today()
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise HTTPException(400, f"Invalid date '{s}', expected YYYY-MM-DD")


def _parse_time(s: str) -> time:
    try:
        h, m = s.split(":")
        return time(int(h), int(m))
    except Exception:
        raise HTTPException(400, f"Invalid time '{s}', expected HH:MM")


def _dt_str(dt) -> str | None:
    return dt.isoformat() if dt else None


def _booking_out(b: BookingSlot) -> BookingSlotOut:
    return BookingSlotOut(
        venue=b.venue,
        sport=b.sport,
        court_id=b.court_id,
        court_number=b.court_number,
        start_time=b.start_time,
        duration_min=b.duration_min,
        price=b.price,
    )


def _rec_out(r: Recommendation) -> RecommendationOut:
    return RecommendationOut(
        venue=r.venue,
        label=r.label,
        rule=r.rule,
        hour=r.hour,
        bookings=[_booking_out(b) for b in r.bookings],
        score=r.score,
    )
