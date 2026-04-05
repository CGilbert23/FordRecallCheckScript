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
