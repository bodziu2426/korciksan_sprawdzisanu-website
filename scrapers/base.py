from dataclasses import dataclass
from datetime import date, time, datetime


@dataclass
class Slot:
    venue: str          # "hasta" | "wsc" | "playmore"
    sport: str          # "squash" | "badminton"
    court_id: str       # raw ID from the site
    court_number: int   # for adjacency checks (1, 2, 3...)
    date: date
    start_time: time
    duration_min: int   # 30 or 60
    is_available: bool
    price: float | None
    scraped_at: datetime
