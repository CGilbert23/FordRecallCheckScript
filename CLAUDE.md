# Recall TXT Checker

## Overview
Flask web app that checks Ford vehicle recalls by VIN using Selenium scraping. Outputs results to Excel files and can email them via Resend.

## Tech Stack
- **Backend:** Python / Flask
- **Scraping:** Selenium (headless browser)
- **Excel:** openpyxl
- **Email:** Resend API
- **Hosting:** DigitalOcean (Docker, Gunicorn)
- **Templates:** Jinja2 HTML (templates/)

## Key Files
- `app.py` — Flask routes and job management (in-memory job store, background threads)
- `recall_checker.py` — Core recall checking logic (Selenium scraping, Excel output)
- `ford_recall_checker_txt.py` — Older/standalone version of the checker
- `templates/` — HTML templates (index, dashboard, status pages)
- `VINS.txt` — Sample VIN list for testing

## Running Locally
```bash
pip install -r requirements.txt
python app.py
# or use run.bat
```

## Environment Variables
- `RESEND_API_KEY` — API key for Resend email service
- `RESEND_FROM_EMAIL` — From address for email (default: fordrecalls@voxapp.co)
- `PROXY_HOST` — IPRoyal residential proxy hostname (e.g. `geo.iproyal.com`)
- `PROXY_PORT` — IPRoyal proxy port (e.g. `12321`)
- `PROXY_USER` — IPRoyal username (may include targeting params like `_country-us`)
- `PROXY_PASS` — IPRoyal password
- All four `PROXY_*` vars must be set together. If any are missing the scraper falls back to direct connection (which Ford will block from DO — see below).

## Why we use a residential proxy
ford.com IP-blocks the DigitalOcean VPS — the recalls page returns "Access Denied — you don't have permission on this server" (Akamai-style block on datacenter IPs). The scraper itself is fine; Ford simply refuses requests from cloud IPs. We route Selenium through an IPRoyal residential proxy so Ford sees a real home-internet IP and serves the page normally. Confirmed 2026-04-29 by reading the body excerpt printed by the `[SCRAPER]` diagnostics in `recall_checker.py`.

If recalls suddenly return 0 again, first suspects in order: (1) proxy credentials expired / out of bandwidth, (2) Ford changed the page selectors, (3) IPRoyal's IP pool itself got flagged. Check `docker logs -f ford-checker` for `[SCRAPER]` lines — `body[0:400]=...` will tell you which.

## Making Changes - Recall Checker
SSH into your VPS, then run these one at a time:
```bash
cd /root/FordRecallCheckScript
git pull
docker build -t ford-checker .
docker stop ford-checker
docker rm ford-checker
docker run -d --name ford-checker -p 5000:10000 --env-file .env ford-checker
```

## Notes
- Jobs run in background threads and results are stored in `outputs/`
- Selenium requires a compatible Chrome/Chromium + ChromeDriver setup
