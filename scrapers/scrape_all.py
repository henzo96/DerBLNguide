#!/usr/bin/env python3
"""
Master scraper — runs all sources and writes data/events.json.
Usage: python scrapers/scrape_all.py
"""

import json
import logging
import sys
import os
from datetime import datetime, timedelta, timezone

# Make sure we can import sibling scripts
sys.path.insert(0, os.path.dirname(__file__))

import scrape_ra
import scrape_rausgegangen
import scrape_tip_berlin
import scrape_filmriss
import scrape_photography_berlin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scrape_all")

# Output path relative to repo root
OUTPUT = os.path.join(os.path.dirname(__file__), "..", "data", "events.json")


def get_week_range() -> tuple[str, str]:
    """Return the Monday of the current week and the Sunday of next week (+13 days)."""
    now = datetime.now()
    # Monday of this week
    days_since_monday = now.weekday()  # 0=Monday
    monday = now - timedelta(days=days_since_monday)
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    # Cover two weeks ahead for buffer
    end = monday + timedelta(days=13)
    return monday.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def dedup(events: list[dict]) -> list[dict]:
    """Remove duplicate events by (title, date, source)."""
    seen = set()
    result = []
    for ev in events:
        key = (
            (ev.get("title") or "").lower().strip(),
            ev.get("date") or "",
            ev.get("source") or "",
        )
        if key not in seen:
            seen.add(key)
            result.append(ev)
    return result


def filter_week(events: list[dict], date_from: str, date_to: str) -> list[dict]:
    return [e for e in events if date_from <= (e.get("date") or "") <= date_to]


def run():
    date_from, date_to = get_week_range()
    logger.info("Week range: %s → %s", date_from, date_to)

    all_events: list[dict] = []
    errors: list[str] = []

    scrapers = [
        ("ra",               scrape_ra,               {"date_from": date_from, "date_to": date_to}),
        ("rausgegangen",     scrape_rausgegangen,     {"date_from": date_from, "date_to": date_to}),
        ("tip-berlin",       scrape_tip_berlin,        {"date_from": date_from, "date_to": date_to}),
        ("filmriss",         scrape_filmriss,          {}),
        ("photography-berlin", scrape_photography_berlin, {}),
    ]

    for name, module, kwargs in scrapers:
        try:
            logger.info("=== Scraping %s ===", name)
            events = module.scrape(**kwargs)
            logger.info("%s: %d events", name, len(events))
            all_events.extend(events)
        except Exception as e:
            logger.error("Scraper %s failed: %s", name, e, exc_info=True)
            errors.append(f"{name}: {e}")

    # Post-process
    all_events = filter_week(all_events, date_from, date_to)
    all_events = dedup(all_events)

    # Assign stable IDs if missing
    for i, ev in enumerate(all_events):
        if not ev.get("id"):
            ev["id"] = f"ev-{i}"

    # Sort by date then time
    all_events.sort(key=lambda e: (e.get("date") or "", e.get("time") or ""))

    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "week_from": date_from,
        "week_to": date_to,
        "total": len(all_events),
        "errors": errors,
        "events": all_events,
    }

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info("Written %d events to %s", len(all_events), OUTPUT)
    if errors:
        logger.warning("Errors: %s", errors)
    return len(errors) == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
