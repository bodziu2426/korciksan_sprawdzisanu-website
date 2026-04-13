"""
WSC calendar HTML dump
-----------------------
Opens wsclub.pl in Playwright, waits for the reservise.com calendar widget to
load, intercepts the JSON response, and saves the full HTML to disk.

Usage:
    python discovery/wsc_calendar_dump.py
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

WSCLUB_URL = "https://wsclub.pl/rezerwacje"
OUT_DIR = Path(__file__).parent

RESOURCES = {
    "squash":    593,
    "badminton": 873,
}


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        captured: dict[str, str] = {}  # sport -> html

        async def handle_response(response):
            for sport, resource_id in RESOURCES.items():
                if (
                    f"/online/{resource_id}/calendar/" in response.url
                    and sport not in captured
                ):
                    try:
                        body = await response.json()
                        if "html" in body:
                            captured[sport] = body["html"]
                            print(f"  captured {sport} ({len(body['html']):,} chars)")
                    except Exception:
                        pass

        page.on("response", handle_response)

        print("Navigating to wsclub.pl ...")
        await page.goto(WSCLUB_URL, timeout=30_000)

        # Wait until we have both sports, up to 15 seconds
        for _ in range(30):
            if set(captured) >= set(RESOURCES):
                break
            await asyncio.sleep(0.5)

        await browser.close()

        if not captured:
            print("Nothing captured — did the page load correctly?")
            return

        for sport, html in captured.items():
            out_file = OUT_DIR / f"wsc_calendar_{sport}.html"
            out_file.write_text(html, encoding="utf-8")
            print(f"Saved {sport} → {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
