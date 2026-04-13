from storage.db import init_db, upsert_slots, get_slots, is_cache_fresh, last_scraped
from scrapers.playmore import scrape as scrape_playmore

# Init DB
init_db()
print("DB initialised.")

# Check cache
venue, sport = "playmore", "squash"
if is_cache_fresh(venue, sport):
    print(f"Cache fresh — skipping scrape.")
else:
    print(f"Cache stale — scraping {venue} {sport}...")
    slots = scrape_playmore(sport)
    upsert_slots(slots)
    print(f"Stored {len(slots)} slots.")

# Query
print(f"\nQuerying available squash slots...")
results = get_slots("squash", available_only=True, venues=["playmore"])
print(f"Found {len(results)} available slots.")

print("\n--- First 5 ---")
for s in results[:5]:
    print(f"  {s.date} {s.start_time}  {s.duration_min}min  court={s.court_number}  venue={s.venue}")

print(f"\nLast scraped: {last_scraped(venue, sport)}")
print(f"Cache fresh:  {is_cache_fresh(venue, sport)}")
