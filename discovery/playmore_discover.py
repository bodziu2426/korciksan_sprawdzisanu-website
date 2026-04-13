"""
Playmore / City Sports Discovery Script
----------------------------------------
Runs a headed Playwright browser on playmore.pl and logs all XHR/fetch
network requests so we can identify the underlying booking API.

Usage:
    python discovery/playmore_discover.py

Browse between squash and badminton tabs, navigate forward/back in the
calendar. All API calls will be printed to the terminal.
Press Ctrl+C or close the browser when done.
"""

import asyncio
import json
from playwright.async_api import async_playwright

SQUASH_URL = "https://playmore.pl/reservation/21/courts?tagId=68"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        def handle_request(request):
            resource_type = request.resource_type
            if resource_type in ("xhr", "fetch"):
                print(f"[{resource_type.upper()}] {request.method} {request.url}")
                try:
                    post_data = request.post_data
                    if post_data:
                        print(f"       BODY: {post_data[:300]}")
                except Exception:
                    pass  # binary/gzip body — skip

        async def handle_response(response):
            resource_type = response.request.resource_type
            if resource_type in ("xhr", "fetch"):
                content_type = response.headers.get("content-type", "-")
                print(f"       --> {response.status} | {content_type}")
                if "json" in content_type:
                    try:
                        body = await response.json()
                        preview = json.dumps(body)[:3000]
                        print(f"       JSON: {preview}")
                    except Exception:
                        pass

        page.on("request", handle_request)
        page.on("response", handle_response)

        print("Opening Playmore squash reservation page...")
        print("Try switching to badminton, navigate calendar weeks.")
        print("All API calls will be logged here.")
        print("Close the browser window when done.\n")

        await page.goto(SQUASH_URL)

        try:
            await page.wait_for_event("close", timeout=0)
        except Exception:
            pass

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
