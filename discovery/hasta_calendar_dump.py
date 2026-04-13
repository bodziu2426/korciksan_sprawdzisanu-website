"""
Hasta la Vista calendar HTML dump
-----------------------------------
Fetches the availability table via httpx and saves full HTML to disk.

Usage:
    python discovery/hasta_calendar_dump.py
"""

import httpx
from datetime import date, timedelta
from pathlib import Path

AJAX_URL = "https://hastalavista.pl/wp-admin/admin-ajax.php"
OUT_DIR = Path(__file__).parent

SPORTS = ["squash", "badminton"]


def dump(sport: str):
    day = date.today() + timedelta(days=1)  # tomorrow — more slots likely available
    out_file = OUT_DIR / f"hasta_calendar_{sport}.html"

    with httpx.Client(follow_redirects=True) as client:
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
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": f"https://hastalavista.pl/rezerwacje/?type={sport}",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=15,
        )
        resp.raise_for_status()
        print(f"[{sport}] status={resp.status_code} content-type={resp.headers.get('content-type')} len={len(resp.text):,}")

    out_file.write_text(resp.text, encoding="utf-8")
    print(f"[{sport}] saved → {out_file}")


if __name__ == "__main__":
    for sport in SPORTS:
        dump(sport)
