import csv
import os
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
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

CSV_FILE = "scholar_papers.csv"
DEFAULT_URL = "https://scholar.google.com/citations?user=-TXOxzIAAAAJ&hl=en"

# simple job state
job_status = {
    "running": False,
    "last_count": 0,
    "error": None
}

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


async def scrape_and_save(url: str):
    global job_status
    job_status["running"] = True
    job_status["error"] = None

    try:
        papers = await scrape_scholar(url)

        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["title", "citations", "year", "link"]
            )
            writer.writeheader()
            writer.writerows(papers)

        job_status["last_count"] = len(papers)

    except Exception as e:
        job_status["error"] = str(e)

    finally:
        job_status["running"] = False


@app.get("/update")
async def update_csv(
    background_tasks: BackgroundTasks,
    url: str = Query(DEFAULT_URL, description="Google Scholar profile URL")
):
    if job_status["running"]:
        return {
            "success": False,
            "message": "Scrape already running"
        }

    background_tasks.add_task(scrape_and_save, url)

    return {
        "success": True,
        "message": "Scraping started in background"
    }


@app.get("/status")
async def status():
    return job_status


@app.get("/download")
def download_csv():
    if not os.path.exists(CSV_FILE):
        raise HTTPException(status_code=404, detail="CSV file not found")

    return FileResponse(
        path=CSV_FILE,
        filename=CSV_FILE,
        media_type="text/csv"
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "google-scholar-scraper"
    }
