"""
WSC Discovery Script
--------------------
Runs a headed Playwright browser on wsclub.pl/rezerwacje and logs all
XHR/fetch network requests so we can identify the underlying booking API.

Usage:
    python discovery/wsc_discover.py

Browse the calendar manually in the browser window that opens.
All API calls will be printed to the terminal.
Press Ctrl+C or close the browser when done.
"""

import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        def handle_request(request):
            resource_type = request.resource_type
            if resource_type in ("xhr", "fetch"):
                print(f"[{resource_type.upper()}] {request.method} {request.url}")
                post_data = request.post_data
                if post_data:
                    print(f"       BODY: {post_data[:300]}")

        def handle_response(response):
            resource_type = response.request.resource_type
            if resource_type in ("xhr", "fetch"):
                print(f"       --> {response.status} | Content-Type: {response.headers.get('content-type', '-')}")

        page.on("request", handle_request)
        page.on("response", handle_response)

        print("Opening WSC reservations page...")
        print("Browse the calendar — all API calls will be logged here.")
        print("Close the browser window when done.\n")

        await page.goto("https://wsclub.pl/rezerwacje")

        # Keep running until browser closes
        try:
            await page.wait_for_event("close", timeout=0)
        except Exception:
            pass

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
