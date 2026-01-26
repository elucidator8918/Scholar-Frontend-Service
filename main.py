import csv
import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright, TimeoutError

app = FastAPI(title="Google Scholar Daily Scraper")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
CSV_FILE = "scholar_papers.csv"
DEFAULT_URL = "https://scholar.google.com/citations?user=-TXOxzIAAAAJ&hl=en"

async def scrape_scholar(url: str):
    p = await async_playwright().start()
    browser = None
    try:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector("#gsc_prf_in", timeout=30000)

        # Click "Show more" until exhausted
        while True:
            try:
                btn = await page.query_selector("#gsc_bpf_more")
                if not btn or await btn.get_attribute("disabled"):
                    break
                await btn.scroll_into_view_if_needed()
                await btn.click()
                await page.wait_for_timeout(1500)
            except TimeoutError:
                break

        papers = await page.evaluate("""
        () => {
            return Array.from(
                document.querySelectorAll("#gsc_a_b .gsc_a_tr")
            ).map(row => {
                const title = row.querySelector(".gsc_a_t a");
                const cites = row.querySelector(".gsc_a_c a");
                const year = row.querySelector(".gsc_a_y span");
                return {
                    title: title?.innerText.trim() || "",
                    link: title ? "https://scholar.google.com" + title.getAttribute("href") : "",
                    citations: cites ? parseInt(cites.innerText) || 0 : 0,
                    year: year?.innerText.trim() || ""
                };
            });
        }
        """)
        return papers

    finally:
        if browser:
            await browser.close()
        await p.stop()


@app.get("/update")
async def update_csv(url: str = Query(DEFAULT_URL, description="Google Scholar profile URL")):
    """Scrapes the profile and updates the CSV file."""
    try:
        papers = await scrape_scholar(url)
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["title", "citations", "year", "link"])
            writer.writeheader()
            writer.writerows(papers)
        return {"success": True, "count": len(papers)}
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Page load timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download")
def download_csv():
    """Returns the latest CSV file as download."""
    if not os.path.exists(CSV_FILE):
        raise HTTPException(status_code=404, detail="CSV file not found")
    return FileResponse(
        path=CSV_FILE,
        filename=CSV_FILE,
        media_type="text/csv"
    )
