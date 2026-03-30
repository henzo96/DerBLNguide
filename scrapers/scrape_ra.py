"""
Scraper for Resident Advisor — de.ra.co/events/de/berlin
Uses the RA GraphQL API (same endpoint the web app uses).
"""

import json
import logging
import re
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)

RA_GRAPHQL = "https://ra.co/graphql"

QUERY = """
query GET_EVENTS_LISTING($filters: FilterInputDtoInput, $pageSize: Int, $page: Int) {
  eventListings(filters: $filters, pageSize: $pageSize, page: $page, sort: { score: DESCENDING, startTime: ASCENDING }) {
    data {
      id
      listingDate
      event {
        id
        title
        date
        startTime
        endTime
        contentUrl
        images { filename }
        venue { name address { address1 city } }
        cost
        pick { blurb }
        artists(first: 5) { name }
      }
    }
  }
}
"""

HEADERS = {
    "Content-Type": "application/json",
    "Referer": "https://ra.co/",
    "Origin": "https://ra.co",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "ra-user-tz": "Europe/Berlin",
}


def fetch_ra_events(date_from: str, date_to: str) -> list[dict]:
    payload = {
        "operationName": "GET_EVENTS_LISTING",
        "variables": {
            "filters": {
                "areas": {"eq": 1},           # Berlin area ID = 1
                "listingDate": {
                    "gte": date_from,
                    "lte": date_to,
                },
            },
            "pageSize": 100,
            "page": 1,
        },
        "query": QUERY,
    }
    try:
        resp = requests.post(RA_GRAPHQL, json=payload, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("eventListings", {}).get("data", [])
    except Exception as e:
        logger.error("RA GraphQL request failed: %s", e)
        return []


def parse_ra_event(listing: dict) -> dict | None:
    ev = listing.get("event")
    if not ev:
        return None

    date_str = (ev.get("date") or listing.get("listingDate") or "")[:10]
    start_time = ev.get("startTime") or ""
    # startTime might be a full ISO string
    if "T" in start_time:
        start_time = start_time[11:16]

    venue = ev.get("venue") or {}
    venue_name = venue.get("name", "")
    addr = (venue.get("address") or {}).get("address1", "")

    # Image
    images = ev.get("images") or []
    image_url = ""
    if images:
        fn = images[0].get("filename", "")
        if fn and fn.startswith("http"):
            image_url = fn
        elif fn:
            image_url = f"https://imgproxy.ra.co/unsafe/{fn}"

    # Description — use pick blurb or artist list
    pick = ev.get("pick") or {}
    desc = pick.get("blurb") or ""
    if not desc:
        artists = ev.get("artists") or []
        if artists:
            desc = ", ".join(a["name"] for a in artists if a.get("name"))

    content_url = ev.get("contentUrl") or ""
    if content_url and not content_url.startswith("http"):
        content_url = "https://ra.co" + content_url

    return {
        "id": f"ra-{ev.get('id', '')}",
        "title": ev.get("title") or "RA Event",
        "date": date_str,
        "time": start_time,
        "end_time": (ev.get("endTime") or "")[:5] if "T" not in (ev.get("endTime") or "") else (ev.get("endTime") or "")[11:16],
        "venue": venue_name,
        "address": addr,
        "category": "music",
        "description": desc[:200] if desc else "",
        "url": content_url,
        "image_url": image_url,
        "price": ev.get("cost") or "",
        "source": "ra",
    }


def scrape(date_from: str, date_to: str) -> list[dict]:
    logger.info("Scraping Resident Advisor %s → %s", date_from, date_to)
    listings = fetch_ra_events(date_from, date_to)
    events = []
    for listing in listings:
        ev = parse_ra_event(listing)
        if ev and ev["date"]:
            events.append(ev)
    logger.info("RA: got %d events", len(events))
    return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    results = scrape(today, end)
    print(json.dumps(results, indent=2, ensure_ascii=False))
