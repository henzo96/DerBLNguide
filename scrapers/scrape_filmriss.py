"""
Scraper for filmriss.club/events
Photography & film events — likely Squarespace or similar.
"""

import json
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.filmriss.club"
EVENTS_URL = f"{BASE_URL}/events"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


def fetch_html() -> str | None:
    import requests
    try:
        resp = requests.get(EVENTS_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning("requests failed for filmriss.club: %s", e)

    # Playwright fallback
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = browser.new_page(user_agent=HEADERS["User-Agent"], locale="de-DE")
            page.goto(EVENTS_URL, wait_until="networkidle", timeout=30000)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        logger.error("Playwright failed for filmriss.club: %s", e)
        return None


MONTH_DE = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4, "mai": 5,
    "juni": 6, "juli": 7, "august": 8, "september": 9,
    "oktober": 10, "november": 11, "dezember": 12,
    # English fallback
    "january": 1, "february": 2, "march": 3, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}


def parse_date(text: str) -> str:
    """Parse dates like '12. März 2026', '12.03.2026', '2026-03-12'."""
    text = text.strip()
    # ISO
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # DD.MM.YYYY
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    # DD. Month YYYY
    m = re.search(r"(\d{1,2})\.\s*([A-Za-zä]+)\s*(\d{4})?", text, re.I)
    if m:
        day = int(m.group(1))
        month_name = m.group(2).lower()
        month = MONTH_DE.get(month_name)
        year = int(m.group(3)) if m.group(3) else datetime.now().year
        if month:
            return f"{year}-{month:02d}-{day:02d}"
    return ""


def parse_time(text: str) -> str:
    m = re.search(r"(\d{1,2}):(\d{2})(?:\s*Uhr)?", text)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    m = re.search(r"(\d{1,2})\s*Uhr", text)
    if m:
        return f"{int(m.group(1)):02d}:00"
    return ""


def parse_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    events = []

    # --- JSON-LD first ---
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") in ("Event", "SocialEvent", "EducationEvent"):
                    start = item.get("startDate") or ""
                    date_str = start[:10] if start else ""
                    time_str = start[11:16] if len(start) > 10 else ""
                    location = item.get("location") or {}
                    venue = location.get("name", "") if isinstance(location, dict) else ""
                    events.append({
                        "id": f"fr-{abs(hash(item.get('name','') + date_str))}",
                        "title": item.get("name") or "",
                        "date": date_str,
                        "time": time_str,
                        "end_time": (item.get("endDate") or "")[11:16] if len(item.get("endDate") or "") > 10 else "",
                        "venue": venue,
                        "address": (location.get("address") or {}).get("streetAddress", "") if isinstance(location, dict) else "",
                        "category": "photography",
                        "description": (item.get("description") or "")[:200],
                        "url": item.get("url") or "",
                        "image_url": (item.get("image") or {}).get("url", "") if isinstance(item.get("image"), dict) else (item.get("image") or ""),
                        "price": "",
                        "source": "filmriss",
                    })
        except Exception:
            pass

    if events:
        return events

    # --- Squarespace / generic event list ---
    # Squarespace uses .eventlist-event or .summary-item
    containers = (
        soup.find_all(class_=re.compile(r"eventlist-event|summary-item|event-item|event-card|entry", re.I))
        or soup.find_all("article")
    )

    for item in containers[:50]:
        # Title
        title_el = item.find(class_=re.compile(r"eventlist-title|summary-title|entry-title|event-title", re.I)) \
                   or item.find(["h1", "h2", "h3"])
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        # Link
        link = title_el.find("a", href=True) or item.find("a", href=True)
        url = ""
        if link:
            href = link["href"]
            url = href if href.startswith("http") else BASE_URL + href

        # Date
        date_el = item.find(class_=re.compile(r"eventlist-date|event-date|summary-date|date|time", re.I)) \
                  or item.find(["time"])
        date_str = ""
        time_str = ""
        if date_el:
            dt_attr = date_el.get("datetime") or date_el.get("data-date") or ""
            if dt_attr:
                date_str = dt_attr[:10]
                time_str = dt_attr[11:16] if len(dt_attr) > 10 else ""
            if not date_str:
                date_str = parse_date(date_el.get_text(strip=True))
                time_str = parse_time(date_el.get_text(strip=True))

        # Venue
        venue_el = item.find(class_=re.compile(r"venue|location|place", re.I))
        venue = venue_el.get_text(strip=True) if venue_el else ""

        # Image
        img = item.find("img", src=True)
        image_url = img.get("data-src") or img["src"] if img else ""
        if image_url and not image_url.startswith("http"):
            image_url = BASE_URL + image_url

        # Description
        desc_el = item.find(class_=re.compile(r"desc|excerpt|body|text|summary-excerpt", re.I))
        desc = desc_el.get_text(strip=True)[:200] if desc_el else ""

        events.append({
            "id": f"fr-{abs(hash(title + date_str))}",
            "title": title,
            "date": date_str,
            "time": time_str,
            "end_time": "",
            "venue": venue,
            "address": "",
            "category": "photography",
            "description": desc,
            "url": url,
            "image_url": image_url,
            "price": "",
            "source": "filmriss",
        })

    return events


def scrape(*args, **kwargs) -> list[dict]:
    logger.info("Scraping filmriss.club")
    html = fetch_html()
    if not html:
        logger.error("Could not fetch filmriss.club")
        return []
    events = parse_html(html)
    logger.info("filmriss.club: got %d events", len(events))
    return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape()
    print(json.dumps(results, indent=2, ensure_ascii=False))
