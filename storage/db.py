"""
SQLite cache for scraped slots
--------------------------------
Schema:
  slots      — one row per venue+sport+court+date+start_time+duration
  scrape_log — tracks when each venue+sport was last successfully scraped

Cache TTL: 15 minutes. Callers should check is_cache_fresh() before deciding
whether to re-scrape.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from scrapers.base import Slot

DB_PATH = Path(__file__).parent.parent / "data" / "slots.db"
CACHE_TTL_MINUTES = 15


# ── Connection ────────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Schema ────────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS slots (
                venue        TEXT    NOT NULL,
                sport        TEXT    NOT NULL,
                court_id     TEXT    NOT NULL,
                court_number INTEGER NOT NULL,
                date         TEXT    NOT NULL,   -- ISO: YYYY-MM-DD
                start_time   TEXT    NOT NULL,   -- HH:MM:SS
                duration_min INTEGER NOT NULL,
                is_available INTEGER NOT NULL,   -- 0/1
                price        REAL,               -- nullable
                scraped_at   TEXT    NOT NULL,   -- ISO datetime
                PRIMARY KEY (venue, sport, court_id, date, start_time, duration_min)
            );

            CREATE TABLE IF NOT EXISTS scrape_log (
                venue      TEXT NOT NULL,
                sport      TEXT NOT NULL,
                scraped_at TEXT NOT NULL,        -- ISO datetime
                PRIMARY KEY (venue, sport)
            );
        """)


# ── Write ─────────────────────────────────────────────────────────────────────

def upsert_slots(slots: list[Slot]) -> None:
    """Insert or replace all slots in one transaction."""
    if not slots:
        return

    rows = [
        (
            s.venue,
            s.sport,
            s.court_id,
            s.court_number,
            s.date.isoformat(),
            s.start_time.isoformat(),
            s.duration_min,
            int(s.is_available),
            s.price,
            s.scraped_at.isoformat(),
        )
        for s in slots
    ]

    with get_connection() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO slots
              (venue, sport, court_id, court_number, date, start_time,
               duration_min, is_available, price, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

        # Update scrape log for each unique venue+sport pair
        pairs = {(s.venue, s.sport) for s in slots}
        now = datetime.now().isoformat()
        conn.executemany(
            "INSERT OR REPLACE INTO scrape_log (venue, sport, scraped_at) VALUES (?, ?, ?)",
            [(v, sp, now) for v, sp in pairs],
        )


# ── Read ──────────────────────────────────────────────────────────────────────

def get_slots(
    sport: str,
    date_from: str | None = None,   # YYYY-MM-DD, inclusive
    date_to: str | None = None,     # YYYY-MM-DD, inclusive
    available_only: bool = True,
    venues: list[str] | None = None,
) -> list[Slot]:
    """
    Query cached slots.

    Args:
        sport:          "squash" or "badminton"
        date_from:      start of date range (defaults to today)
        date_to:        end of date range (defaults to 7 days out)
        available_only: if True, only return is_available=1 slots
        venues:         filter to specific venues (default: all)

    Returns:
        List of Slot objects ordered by date, start_time, venue, court_number.
    """
    from datetime import date

    if date_from is None:
        date_from = date.today().isoformat()
    if date_to is None:
        date_to = (date.today() + timedelta(days=7)).isoformat()

    conditions = ["sport = ?", "date >= ?", "date <= ?"]
    params: list = [sport, date_from, date_to]

    if available_only:
        conditions.append("is_available = 1")

    if venues:
        placeholders = ",".join("?" * len(venues))
        conditions.append(f"venue IN ({placeholders})")
        params.extend(venues)

    where = " AND ".join(conditions)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM slots
            WHERE {where}
            ORDER BY date, start_time, venue, court_number
            """,
            params,
        ).fetchall()

    return [_row_to_slot(r) for r in rows]


def is_cache_fresh(venue: str, sport: str) -> bool:
    """Return True if venue+sport was scraped within the last CACHE_TTL_MINUTES."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT scraped_at FROM scrape_log WHERE venue = ? AND sport = ?",
            (venue, sport),
        ).fetchone()

    if row is None:
        return False

    scraped_at = datetime.fromisoformat(row["scraped_at"])
    return datetime.now() - scraped_at < timedelta(minutes=CACHE_TTL_MINUTES)


def last_scraped(venue: str, sport: str) -> datetime | None:
    """Return when venue+sport was last scraped, or None if never."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT scraped_at FROM scrape_log WHERE venue = ? AND sport = ?",
            (venue, sport),
        ).fetchone()
    return datetime.fromisoformat(row["scraped_at"]) if row else None


# ── Internal ──────────────────────────────────────────────────────────────────

def _row_to_slot(row: sqlite3.Row) -> Slot:
    from datetime import date, time
    return Slot(
        venue=row["venue"],
        sport=row["sport"],
        court_id=row["court_id"],
        court_number=row["court_number"],
        date=date.fromisoformat(row["date"]),
        start_time=time.fromisoformat(row["start_time"]),
        duration_min=row["duration_min"],
        is_available=bool(row["is_available"]),
        price=row["price"],
        scraped_at=datetime.fromisoformat(row["scraped_at"]),
    )
