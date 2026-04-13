from datetime import date, time
from pydantic import BaseModel


class BookingSlotOut(BaseModel):
    venue: str
    sport: str
    court_id: str
    court_number: int
    start_time: time
    duration_min: int
    price: float | None


class RecommendationOut(BaseModel):
    venue: str
    label: str
    rule: str
    hour: time
    bookings: list[BookingSlotOut]
    score: float


class SearchResponse(BaseModel):
    date: date
    sport: str
    persons: int
    time_from: time | None
    time_to: time | None
    recommendations: list[RecommendationOut]
    cache_info: dict[str, str]   # venue+sport -> "fresh" | "refreshed" | "failed"


class VenueStatus(BaseModel):
    venue: str
    sport: str
    cache_fresh: bool
    last_scraped: str | None     # ISO datetime or None


class RefreshResponse(BaseModel):
    venue: str
    sport: str
    slots_stored: int
    status: str
