import csv
import os
import re
import asyncio
from urllib.parse import urlparse, parse_qs

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from scholarly import scholarly

app = FastAPI(title="Google Scholar Daily Scraper")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CSV_FILE = "scholar_papers.csv"

DEFAULT_URL = (
    "https://scholar.google.com/citations?"
    "user=-TXOxzIAAAAJ&hl=en"
)

# Job state
job_status = {
    "running": False,
    "last_count": 0,
    "error": None,
    "author": None,
    "total_citations": 0,
    "h_index": 0,
    "i10_index": 0,
    "last_updated": None
}


def extract_author_id(url: str) -> str:
    """Extract Google Scholar author ID from profile URL."""

    parsed = urlparse(url)
    author_id = parse_qs(parsed.query).get("user", [None])[0]

    if not author_id:
        # Also allow a raw author ID.
        if re.fullmatch(r"[-\w]+", url):
            return url

        raise ValueError("Invalid Google Scholar profile URL or author ID")

    return author_id


def scrape_scholar(author_id: str):
    """
    Retrieve author profile and publication details using scholarly.
    """

    author = scholarly.search_author_id(author_id)

    # Fill profile information and publication list.
    author = scholarly.fill(author)

    author_metrics = {
        "name": author.get("name", ""),
        "total_citations": author.get("citedby", 0),
        "h_index": author.get("hindex", 0),
        "i10_index": author.get("i10index", 0),
        "citations_per_year": author.get("cites_per_year", {})
    }

    papers = []

    for pub in author.get("publications", []):

        bib = pub.get("bib", {})

        title = bib.get("title", "")

        if not title:
            continue

        citations = pub.get("num_citations", 0) or 0

        # Construct Google Scholar publication URL.
        pub_id = pub.get("author_pub_id", "")

        link = ""

        if pub_id:
            link = (
                "https://scholar.google.com/citations?"
                f"view_op=view_citation&hl=en&user={author_id}"
                f"&citation_for_view={pub_id}"
            )

        papers.append({
            "title": title,
            "citations": citations,
            "year": bib.get("pub_year", ""),
            "link": link
        })

    return author_metrics, papers


async def scrape_and_save(url: str):
    global job_status

    job_status["running"] = True
    job_status["error"] = None

    try:
        author_id = extract_author_id(url)

        # scholarly is synchronous, so run it outside the async event loop.
        author_metrics, papers = await asyncio.to_thread(
            scrape_scholar,
            author_id
        )

        with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:

            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "title",
                    "citations",
                    "year",
                    "link"
                ]
            )

            writer.writeheader()
            writer.writerows(papers)

        from datetime import datetime, timezone

        job_status.update({
            "last_count": len(papers),
            "author": author_metrics["name"],
            "total_citations": author_metrics["total_citations"],
            "h_index": author_metrics["h_index"],
            "i10_index": author_metrics["i10_index"],
            "citations_per_year": author_metrics["citations_per_year"],
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "error": None
        })

    except Exception as e:
        job_status["error"] = str(e)
        print(f"Google Scholar scraping error: {e}")

    finally:
        job_status["running"] = False


@app.get("/update")
async def update_csv(
    background_tasks: BackgroundTasks,
    url: str = Query(
        DEFAULT_URL,
        description="Google Scholar profile URL or author ID"
    )
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
        raise HTTPException(
            status_code=404,
            detail="CSV file not found"
        )

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
