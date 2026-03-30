"""
Scraper for photography-in.berlin/current/
Exhibitions listing — typically server-side rendered (WordPress or similar CMS).
Falls back to Playwright if requests gets blocked.
"""

import json
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.photography-in.berlin"
CURRENT_URL = f"{BASE_URL}/current/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}


def fetch_with_requests() -> str | None:
    import requests
    try:
        resp = requests.get(CURRENT_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning("requests failed for photography-in.berlin: %s", e)
        return None


def fetch_with_playwright() -> str | None:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = browser.new_page(
                user_agent=HEADERS["User-Agent"],
                locale="de-DE",
                timezone_id="Europe/Berlin",
            )
            page.goto(CURRENT_URL, wait_until="networkidle", timeout=30000)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        logger.error("Playwright failed for photography-in.berlin: %s", e)
        return None


def parse_date_range(text: str) -> tuple[str, str]:
    """Try to extract date range from text like 'bis 15.04.2026' or '01.03. – 30.04.2026'."""
    # Pattern: DD.MM.YYYY
    dates = re.findall(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if dates:
        # Return first and last date found
        def to_iso(d):
            return f"{d[2]}-{int(d[1]):02d}-{int(d[0]):02d}"
        if len(dates) >= 2:
            return to_iso(dates[0]), to_iso(dates[-1])
        return to_iso(dates[0]), to_iso(dates[0])
    # Pattern: DD.MM. (no year) — infer current year
    partial = re.findall(r"(\d{1,2})\.(\d{1,2})\.", text)
    year = datetime.now().year
    if partial:
        def to_iso_partial(d):
            m = int(d[1])
            y = year if m >= datetime.now().month else year + 1
            return f"{y}-{m:02d}-{int(d[0]):02d}"
        if len(partial) >= 2:
            return to_iso_partial(partial[0]), to_iso_partial(partial[-1])
        return to_iso_partial(partial[0]), to_iso_partial(partial[0])
    return "", ""


def parse_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    events = []

    # --- Try JSON-LD first ---
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") in ("ExhibitionEvent", "Event", "VisualArtsEvent"):
                    start = (item.get("startDate") or "")[:10]
                    end = (item.get("endDate") or "")[:10]
                    location = item.get("location") or {}
                    venue = location.get("name", "") if isinstance(location, dict) else str(location)
                    events.append({
                        "id": f"pb-{hash(item.get('name',''))}",
                        "title": item.get("name") or "",
                        "date": start or end,
                        "time": "",
                        "end_time": end,
                        "venue": venue,
                        "address": "",
                        "category": "exhibition",
                        "description": (item.get("description") or "")[:200],
                        "url": item.get("url") or item.get("@id") or "",
                        "image_url": (item.get("image") or {}).get("url", "") if isinstance(item.get("image"), dict) else (item.get("image") or ""),
                        "price": "",
                        "source": "photography-berlin",
                    })
        except Exception:
            pass

    if events:
        return events

    # --- Fallback: look for common exhibition list structures ---
    selectors = [
        ("article", None),
        ("div", "exhibition"),
        ("div", "event"),
        ("div", "listing"),
        ("li", "exhibition"),
    ]

    for tag, klass in selectors:
        if klass:
            items = soup.find_all(tag, class_=re.compile(klass, re.I))
        else:
            items = soup.find_all(tag)
        if not items:
            continue

        for item in items[:50]:
            # Title
            title_el = (
                item.find(["h1", "h2", "h3", "h4"])
                or item.find(class_=re.compile(r"title|name|heading", re.I))
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            # URL
            link = item.find("a", href=True)
            url = ""
            if link:
                href = link["href"]
                url = href if href.startswith("http") else BASE_URL + href

            # Dates
            date_text = item.get_text(" ", strip=True)
            date_from, date_to = parse_date_range(date_text)

            # Venue
            venue_el = item.find(class_=re.compile(r"venue|location|gallery|museum", re.I))
            venue = venue_el.get_text(strip=True) if venue_el else ""

            # Image
            img = item.find("img", src=True)
            image_url = img["src"] if img else ""
            if image_url and not image_url.startswith("http"):
                image_url = BASE_URL + image_url

            # Description
            desc_el = item.find(class_=re.compile(r"desc|text|body|excerpt|summary", re.I))
            desc = desc_el.get_text(strip=True)[:200] if desc_el else ""

            events.append({
                "id": f"pb-{abs(hash(title + date_from))}",
                "title": title,
                "date": date_from,
                "time": "",
                "end_time": date_to,
                "venue": venue,
                "address": "",
                "category": "exhibition",
                "description": desc,
                "url": url,
                "image_url": image_url,
                "price": "",
                "source": "photography-berlin",
            })

        if events:
            break

    return events


def scrape(*args, **kwargs) -> list[dict]:
    logger.info("Scraping photography-in.berlin")
    html = fetch_with_requests()
    if not html:
        html = fetch_with_playwright()
    if not html:
        logger.error("Could not fetch photography-in.berlin")
        return []
    events = parse_html(html)
    logger.info("photography-in.berlin: got %d events", len(events))
    return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape()
    print(json.dumps(results, indent=2, ensure_ascii=False))
