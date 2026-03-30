"""
Scraper for tip-berlin.de/event/
Berlin magazine events page — likely WordPress with Event Calendar plugin.
"""

import json
import logging
import re
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tip-berlin.de"
EVENTS_URL = f"{BASE_URL}/event/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9",
}


def fetch_html(url: str = EVENTS_URL) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning("requests failed for tip-berlin %s: %s", url, e)

    # Playwright fallback
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = browser.new_page(user_agent=HEADERS["User-Agent"], locale="de-DE")
            page.goto(url, wait_until="networkidle", timeout=30000)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        logger.error("Playwright failed for tip-berlin: %s", e)
        return None


# WordPress REST API — if available
def try_wp_api(date_from: str, date_to: str) -> list[dict]:
    wp_api = f"{BASE_URL}/wp-json/tribe/events/v1/events"
    params = {
        "start_date": date_from,
        "end_date": date_to,
        "per_page": 100,
        "page": 1,
    }
    try:
        resp = requests.get(wp_api, params=params, headers=HEADERS, timeout=15)
        if resp.status_code == 200 and "json" in resp.headers.get("content-type", ""):
            data = resp.json()
            return data.get("events", [])
    except Exception:
        pass
    return []


def parse_wp_event(ev: dict) -> dict:
    start = ev.get("start_date") or ev.get("start_date_details", {}).get("date", "") or ""
    date_str = start[:10] if start else ""
    time_str = start[11:16] if len(start) > 10 else ""
    venue = (ev.get("venue") or {}).get("venue") or ""
    addr = (ev.get("venue") or {}).get("address") or ""
    img = (ev.get("image") or {})
    image_url = img.get("url") or img.get("sizes", {}).get("medium", {}).get("url", "") if isinstance(img, dict) else ""
    categories = [c.get("name", "") for c in (ev.get("categories") or []) if c.get("name")]
    cat = "general"
    for c in categories:
        cl = c.lower()
        if "musik" in cl or "music" in cl or "konzert" in cl or "club" in cl:
            cat = "music"
            break
        if "foto" in cl or "photo" in cl or "ausstellung" in cl or "exhibition" in cl:
            cat = "exhibition"
            break
    return {
        "id": f"tb-{ev.get('id', abs(hash(ev.get('title','') + date_str)))}",
        "title": ev.get("title") or "",
        "date": date_str,
        "time": time_str,
        "end_time": (ev.get("end_date") or "")[11:16] if len(ev.get("end_date") or "") > 10 else "",
        "venue": venue,
        "address": addr,
        "category": cat,
        "description": re.sub(r"<[^>]+>", "", ev.get("description") or "")[:200],
        "url": ev.get("url") or "",
        "image_url": image_url,
        "price": ev.get("cost") or "",
        "source": "tip-berlin",
    }


def parse_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    events = []

    # JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") in ("Event", "MusicEvent", "Festival", "SocialEvent", "TheaterEvent"):
                    start = item.get("startDate") or ""
                    date_str = start[:10]
                    time_str = start[11:16] if len(start) > 10 else ""
                    loc = item.get("location") or {}
                    venue = loc.get("name", "") if isinstance(loc, dict) else ""
                    img = item.get("image")
                    image_url = img.get("url", "") if isinstance(img, dict) else (img or "")
                    cat_map = {"MusicEvent": "music", "Festival": "general"}
                    cat = cat_map.get(item.get("@type"), "general")
                    events.append({
                        "id": f"tb-{abs(hash(item.get('name','') + date_str))}",
                        "title": item.get("name") or "",
                        "date": date_str,
                        "time": time_str,
                        "end_time": (item.get("endDate") or "")[11:16] if len(item.get("endDate") or "") > 10 else "",
                        "venue": venue,
                        "address": "",
                        "category": cat,
                        "description": (item.get("description") or "")[:200],
                        "url": item.get("url") or "",
                        "image_url": image_url,
                        "price": "",
                        "source": "tip-berlin",
                    })
        except Exception:
            pass

    if events:
        return events

    # WordPress Tribe Events plugin selectors
    for card in soup.find_all(class_=re.compile(r"tribe-event|type-tribe|events-list|event-item", re.I))[:60]:
        title_el = card.find(class_=re.compile(r"tribe-event-title|entry-title|event-title", re.I)) \
                   or card.find(["h2", "h3"])
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link = card.find("a", href=True)
        url = link["href"] if link else ""

        date_el = card.find(class_=re.compile(r"tribe-event-date|event-date|date", re.I)) \
                  or card.find("time")
        date_str, time_str = "", ""
        if date_el:
            dt = date_el.get("datetime") or ""
            date_str = dt[:10] if dt else ""
            time_str = dt[11:16] if len(dt) > 10 else ""

        venue_el = card.find(class_=re.compile(r"tribe-venue|venue|location", re.I))
        venue = venue_el.get_text(strip=True) if venue_el else ""

        img = card.find("img", src=True)
        image_url = img.get("data-src") or img["src"] if img else ""

        events.append({
            "id": f"tb-{abs(hash(title + date_str))}",
            "title": title,
            "date": date_str,
            "time": time_str,
            "end_time": "",
            "venue": venue,
            "address": "",
            "category": "general",
            "description": "",
            "url": url,
            "image_url": image_url,
            "price": "",
            "source": "tip-berlin",
        })

    return events


def scrape(date_from: str, date_to: str) -> list[dict]:
    logger.info("Scraping tip-berlin.de %s → %s", date_from, date_to)

    # 1. Try WordPress REST API (The Events Calendar plugin)
    events = [parse_wp_event(e) for e in try_wp_api(date_from, date_to)]
    if events:
        logger.info("tip-berlin WP API: got %d events", len(events))
        return events

    # 2. HTML scrape
    html = fetch_html()
    if not html:
        logger.error("Could not fetch tip-berlin.de")
        return []
    events = parse_html(html)
    logger.info("tip-berlin HTML: got %d events", len(events))
    return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    results = scrape(today, end)
    print(json.dumps(results, indent=2, ensure_ascii=False))
