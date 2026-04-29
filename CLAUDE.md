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
- Both must be set together. If either is missing the scraper falls back to direct connection (which Ford will block from DO — see below).
- Auth is via **IP whitelist** in the IPRoyal dashboard, not user/pass. The VPS's outbound IP is allowed there, so no credentials are sent. If the VPS IP ever changes, update the whitelist (look it up with `docker exec ford-checker python -c "import urllib.request; print(urllib.request.urlopen('https://ipv4.icanhazip.com').read().decode().strip())"`).

## Why we use a residential proxy
ford.com IP-blocks the DigitalOcean VPS — the recalls page returns "Access Denied — you don't have permission on this server" (Akamai-style block on datacenter IPs). The scraper itself is fine; Ford simply refuses requests from cloud IPs. We route Chrome through an IPRoyal residential proxy via `--proxy-server` so Ford sees a real home-internet IP and serves the page normally. Confirmed 2026-04-29.

We tried selenium-wire first to handle user/pass auth, but it had cascading dependency issues (`pkg_resources` removed in newer setuptools, mitmproxy auth-forwarding bugs). IP whitelist auth is simpler — Chrome's native `--proxy-server` flag works fine when the proxy doesn't ask for credentials.

If recalls suddenly return 0 again, first suspects in order: (1) VPS outbound IP changed and is no longer in IPRoyal's whitelist, (2) IPRoyal bandwidth quota exhausted, (3) Ford changed the page selectors, (4) IPRoyal's IP pool itself got flagged. Check `docker logs -f ford-checker` for `[SCRAPER]` lines — `body[0:400]=...` will tell you which.

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
