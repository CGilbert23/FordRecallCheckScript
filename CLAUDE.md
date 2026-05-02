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
- `USE_GH_ACTIONS_FOR_RECALLS` — set to `1` on hosts whose egress IP is blocked
  by Ford's Akamai (DigitalOcean prod, Fly, etc.). Routes recall checks through
  the `recall_check_on_demand` workflow in this same repo (which runs on
  GitHub-hosted Azure IPs that Akamai allows). Leave unset for local dev —
  residential IPs aren't blocked.
- `GH_ACTIONS_TOKEN` — GitHub PAT (`actions:write` + `actions:read` on
  `CGilbert23/FordRecallCheckScript`); required when the flag above is set.
- `GH_ACTIONS_REPO` — target repo, e.g. `CGilbert23/FordRecallCheckScript`.
- `GH_ACTIONS_WORKFLOW` — workflow filename, default `recall_check_on_demand.yml`.
- `GH_ACTIONS_REF` — branch to dispatch against, default `main`.

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
