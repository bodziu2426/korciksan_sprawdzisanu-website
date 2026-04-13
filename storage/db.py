# SQLite cache for scraped slots
# TODO: implement schema and CRUD operations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "slots.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    return sqlite3.connect(DB_PATH)
