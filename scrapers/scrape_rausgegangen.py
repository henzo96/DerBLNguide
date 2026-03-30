"""
Scraper for rausgegangen.de/berlin/
Major German events aggregator — JS-heavy SPA.
Uses Playwright to render, then parses the result.
Also tries the internal API endpoint rausgegangen sometimes exposes.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://rausgegangen.de"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "de-DE,de;q=0.9",
    "Referer": "https://rausgegangen.de/berlin/",
}


def try_api(date_from: str, date_to: str) -> list[dict] | None:
    """Attempt to use rausgegangen's internal API / search endpoint."""
    # Known internal API patterns used by rausgegangen SPA
    endpoints = [
        f"{BASE_URL}/api/events?city=berlin&from={date_from}&to={date_to}&limit=100",
        f"{BASE_URL}/api/v1/events?city=berlin&startDate={date_from}&endDate={date_to}",
        f"https://api.rausgegangen.de/events?city=berlin&from={date_from}&to={date_to}",
    ]
    for url in endpoints:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json"):
                return resp.json()
        except Exception:
            pass
    return None


def fetch_with_playwright(date_from: str, date_to: str) -> list[dict]:
    """Use Playwright to scrape the Berlin events page, intercept API calls."""
    events_data = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            ctx = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="de-DE",
                timezone_id="Europe/Berlin",
            )

            # Intercept JSON API responses
            def handle_response(response):
                if "api" in response.url.lower() and "event" in response.url.lower():
                    try:
                        if response.status == 200 and "json" in response.headers.get("content-type", ""):
                            data = response.json()
                            if isinstance(data, list):
                                events_data.extend(data)
                            elif isinstance(data, dict) and "events" in data:
                                events_data.extend(data["events"])
                            elif isinstance(data, dict) and "data" in data:
                                d = data["data"]
                                if isinstance(d, list):
                                    events_data.extend(d)
                    except Exception:
                        pass

            page = ctx.new_page()
            page.on("response", handle_response)
            page.goto(f"{BASE_URL}/berlin/", wait_until="networkidle", timeout=30000)
            # Scroll to trigger lazy loading
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)

            if not events_data:
                # Fall back to parsing rendered HTML
                html = page.content()
                browser.close()
                return parse_rendered_html(html)

            browser.close()
            return events_data
    except Exception as e:
        logger.error("Playwright failed for rausgegangen: %s", e)
        return []


def parse_rendered_html(html: str) -> list[dict]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    events = []

    # JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") in ("Event", "MusicEvent", "Festival", "SocialEvent"):
                    start = item.get("startDate") or ""
                    events.append(_from_jsonld(item, "rausgegangen"))
        except Exception:
            pass

    if events:
        return events

    # Generic article cards
    for card in soup.find_all(class_=re.compile(r"event|card|item|listing", re.I))[:60]:
        title_el = card.find(["h2", "h3", "h4"]) or card.find(class_=re.compile(r"title|name", re.I))
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link = card.find("a", href=True)
        url = ""
        if link:
            h = link["href"]
            url = h if h.startswith("http") else BASE_URL + h
        date_el = card.find(class_=re.compile(r"date|time|when", re.I)) or card.find("time")
        date_str, time_str = "", ""
        if date_el:
            dt = date_el.get("datetime") or ""
            date_str = dt[:10] if dt else ""
            time_str = dt[11:16] if len(dt) > 10 else ""
        events.append({
            "id": f"rg-{abs(hash(title + date_str))}",
            "title": title,
            "date": date_str,
            "time": time_str,
            "end_time": "",
            "venue": "",
            "address": "",
            "category": "general",
            "description": "",
            "url": url,
            "image_url": "",
            "price": "",
            "source": "rausgegangen",
        })
    return events


def _from_jsonld(item: dict, source: str) -> dict:
    start = item.get("startDate") or ""
    date_str = start[:10] if start else ""
    time_str = start[11:16] if len(start) > 10 else ""
    loc = item.get("location") or {}
    venue = loc.get("name", "") if isinstance(loc, dict) else ""
    addr = (loc.get("address") or {}).get("streetAddress", "") if isinstance(loc, dict) else ""
    img = item.get("image")
    image_url = ""
    if isinstance(img, dict):
        image_url = img.get("url", "")
    elif isinstance(img, str):
        image_url = img
    cat_map = {
        "MusicEvent": "music",
        "Festival": "general",
        "ExhibitionEvent": "exhibition",
        "VisualArtsEvent": "exhibition",
    }
    cat = cat_map.get(item.get("@type"), "general")
    return {
        "id": f"{source[:2]}-{abs(hash(item.get('name','') + date_str))}",
        "title": item.get("name") or "",
        "date": date_str,
        "time": time_str,
        "end_time": (item.get("endDate") or "")[11:16] if len(item.get("endDate") or "") > 10 else "",
        "venue": venue,
        "address": addr,
        "category": cat,
        "description": (item.get("description") or "")[:200],
        "url": item.get("url") or "",
        "image_url": image_url,
        "price": item.get("offers", {}).get("price", "") if isinstance(item.get("offers"), dict) else "",
        "source": source,
    }


def normalise_api_event(raw: dict) -> dict | None:
    """Convert a raw API dict from rausgegangen to our schema."""
    # Try common field names
    title = raw.get("title") or raw.get("name") or raw.get("headline") or ""
    if not title:
        return None

    date_raw = raw.get("date") or raw.get("startDate") or raw.get("start_date") or raw.get("startTime") or ""
    date_str = date_raw[:10] if date_raw else ""
    time_str = date_raw[11:16] if len(date_raw) > 10 else ""

    venue_raw = raw.get("venue") or raw.get("location") or {}
    if isinstance(venue_raw, dict):
        venue = venue_raw.get("name") or venue_raw.get("title") or ""
        addr = venue_raw.get("address") or ""
    else:
        venue = str(venue_raw)
        addr = ""

    cat_raw = (raw.get("category") or raw.get("type") or "").lower()
    if "music" in cat_raw or "concert" in cat_raw or "club" in cat_raw:
        cat = "music"
    elif "photo" in cat_raw or "exhibition" in cat_raw or "ausstellung" in cat_raw:
        cat = "exhibition"
    else:
        cat = "general"

    img = raw.get("image") or raw.get("imageUrl") or raw.get("thumbnail") or ""
    url = raw.get("url") or raw.get("link") or raw.get("externalUrl") or ""

    return {
        "id": f"rg-{raw.get('id') or abs(hash(title + date_str))}",
        "title": title,
        "date": date_str,
        "time": time_str,
        "end_time": "",
        "venue": venue,
        "address": addr,
        "category": cat,
        "description": (raw.get("description") or raw.get("body") or "")[:200],
        "url": url,
        "image_url": img if isinstance(img, str) else (img.get("url") or "") if isinstance(img, dict) else "",
        "price": str(raw.get("price") or ""),
        "source": "rausgegangen",
    }


def scrape(date_from: str, date_to: str) -> list[dict]:
    logger.info("Scraping rausgegangen.de %s → %s", date_from, date_to)

    # 1. Try API
    raw = try_api(date_from, date_to)
    if raw:
        logger.info("rausgegangen: API returned %d items", len(raw))
        items = raw if isinstance(raw, list) else raw.get("events", [])
        events = [e for e in (normalise_api_event(r) for r in items) if e]
        if events:
            return events

    # 2. Playwright fallback
    raw_events = fetch_with_playwright(date_from, date_to)
    if not raw_events:
        return []

    if isinstance(raw_events, list) and raw_events and isinstance(raw_events[0], dict):
        # Could be already-parsed dicts from HTML or raw API dicts
        if "source" in raw_events[0]:
            return raw_events  # already normalised
        events = [e for e in (normalise_api_event(r) for r in raw_events) if e]
    else:
        events = raw_events

    logger.info("rausgegangen: got %d events", len(events))
    return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    results = scrape(today, end)
    print(json.dumps(results, indent=2, ensure_ascii=False))
