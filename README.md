# DerBLNguide

**Your weekly Berlin events guide** — music, photography, exhibitions, and festivals, all in one place.

## What it does

- Shows every day of the current week with its events
- Organised by category: General/Festivals · Music · Photography Events · Photography Exhibitions
- Updates automatically twice a day via GitHub Actions
- Works beautifully on iPhone Safari (and all other browsers)

## Data sources

| Category | Source |
|---|---|
| General / Festivals | [Rausgegangen](https://rausgegangen.de/berlin/), [Tip Berlin](https://www.tip-berlin.de/event/) |
| Music | [Resident Advisor](https://de.ra.co/events/de/berlin) |
| Photography Events | [Filmriss Club](https://www.filmriss.club/events) |
| Photography Exhibitions | [Photography in Berlin](https://www.photography-in.berlin/current/) |

## How it works

```
GitHub Actions (cron: 05:00 + 14:00 Berlin time)
    │
    └─▶ scrapers/scrape_all.py
            ├─ scrape_ra.py            (RA GraphQL API)
            ├─ scrape_rausgegangen.py  (Playwright + JSON-LD)
            ├─ scrape_tip_berlin.py    (WP REST API + BeautifulSoup)
            ├─ scrape_filmriss.py      (BeautifulSoup + Playwright)
            └─ scrape_photography_berlin.py
                    │
                    └─▶ data/events.json  ──▶  GitHub Pages
```

The frontend (`index.html`) is a zero-dependency static page served by GitHub Pages that reads `data/events.json`.

## Running scrapers locally

```bash
cd scrapers
pip install -r requirements.txt
playwright install chromium
python scrape_all.py
```

## Enabling GitHub Pages

1. Go to **Settings → Pages** in this repo
2. Set source to **Deploy from a branch**, branch `main`, folder `/` (root)
3. Save — your site will be live at `https://<your-username>.github.io/DerBLNguide/`

## Manual scrape trigger

Go to **Actions → Scrape Berlin Events → Run workflow** to trigger a scrape immediately.
