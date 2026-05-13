# Fred Beans Mobile Service

## Overview
Internal Flask app for the mobile service team. Four top-level sections:
- **Account Management** — existing customer accounts and new leads (CRM)
- **Recall Checker** — Ford VIN recall lookups (one-time, scheduled, run log)
- **Used Car Tracker** — iframes an external Vercel app (`used-car-lot-recall-sweeper.vercel.app`) that sweeps used-car lot inventory for open recalls
- **Mobile Keys** — Key Database for tracking each key cut (vehicle, parts + costs, P&L). One row per key with computed totals/discount/final charge on display.

Recall data is scraped via Selenium, results are written to Excel and emailed via Resend. Account/lead/schedule data lives in Supabase Postgres.

**Production URL:** http://dashboard.fredbeans-mobileservice.com/ (DigitalOcean droplet, nginx reverse-proxies port 80 → container on `127.0.0.1:5000`). Domain `fredbeans-mobileservice.com` is owned by the user; the `dashboard` A record points at the droplet. The old `recallchecker.fredbeans-mobileservice.com` hostname was retired on 2026-05-10 — DNS record was renamed (not duplicated), and the nginx `server_name` in `/etc/nginx/sites-available/recallchecker` was updated to match.

## Tech Stack
- **Backend:** Python / Flask (single-file app, no blueprints)
- **DB:** Supabase Postgres (via `supabase-py`)
- **Scraping:** Selenium (headless Chromium)
- **Excel:** openpyxl
- **Email:** Resend API
- **Scheduler:** APScheduler (cron triggers, single-process)
- **Hosting:** DigitalOcean (Docker, Gunicorn)
- **Templates:** Jinja2 HTML in `templates/` with inline CSS (no framework)

## Routes (high-level)
- `/` — home tile page (Account Management / Recall Checker)
- `/accounts` and `/accounts/new`, `/accounts/<id>/edit`, `/accounts/<id>/delete`
- `/leads` and `/leads/new`, `/leads/<id>/edit`, `/leads/<id>/delete`, `/leads/<id>/convert` (lead → account). `/leads/new?type=warm` defaults the form to warm.
- `/leads/<id>/promote` (GET) — renders the lead form pre-filled with `lead_type=warm` so the rep can fill in warm-only fields before posting to `/leads/<id>/edit` to save.
- `/leads/<id>/attempt` (POST) — record a contact attempt (`outcome` = `made_contact` or `left_voicemail`). A note is required server-side for `made_contact`; voicemail attempts always store a null note.
- `/leads/<id>/last-contacted` (POST) — inline update of just `last_contacted_at` from the warm-prospect table (no full edit form).
- `/recall-checker` — one-time VIN check form (posts to `/submit`). Accepts `?account_id=<id>` to prefill VINs and customer name from an account.
- `/recall/run-log` — recent jobs (in-memory only, lost on restart)
- `/schedules` and children — recurring recall checks
- `/notes` (GET/POST) — shared scratchpad page under Account Management. Auto-saves a couple seconds after typing stops via JSON POST; falls back to a normal form POST if JS is off. `beforeunload` fires `navigator.sendBeacon` to save on tab close.
- `/dashboard` — 302 redirect to `/recall/run-log` (back-compat)
- `/mobile-keys` — Key Database list (table of all rows, newest first). Row actions: Edit + Inventory only — Delete is reachable only from the edit form.
- `/mobile-keys/new`, `/mobile-keys/<id>/edit`, `/mobile-keys/<id>/delete` — CRUD endpoints
- `/mobile-keys/<id>/toggle-status` (POST) — flips the per-row `status_done` checkbox in the leftmost Status column. Unchecked rows render with a light-grey row tint.
- `/mobile-keys/<id>/move-to-inventory`, `/mobile-keys/<id>/restore-from-inventory` — toggle the inventory flag on a key
- `/mobile-keys/inventory` — Inventory list (parts that were ordered but the customer no longer needs them; shows Date/Year/Make/Model + part numbers and costs only)
- `/test-supabase`, `/test-chrome` — health checks

## Key Files
- `app.py` — Flask routes, in-memory job store, queue worker thread
- `db.py` — Supabase client + CRUD for schedules/accounts/leads + constants (`MARKETS`, `ACCOUNT_REPS`, `SERVICE_TYPES`, `LEAD_SOURCES`, `LEAD_SOURCES_WITH_CONTACT`, `LEAD_TYPES`, `INTEREST_LEVELS`, `INTEREST_LEVEL_DEFAULT`, `LEAD_ATTEMPT_OUTCOMES`, `LEAD_CLOSE_REASONS`, `CADENCES`). `LOCATIONS` is an alias for `MARKETS`. `LEAD_SOURCES` includes `Sales`, `Service`, `Parts`, `Visual`, `Other`; `LEAD_SOURCES_WITH_CONTACT` is the subset that exposes the free-text `source_contact` field on the form.
- `scheduler.py` — APScheduler integration for recurring schedules
- `recall_checker.py` — Selenium scraping + Excel output
- `gh_actions_client.py` / `run_on_demand.py` — fallback path that runs the scrape via GitHub Actions (used when the host IP is blocked by Ford's Akamai)
- `ford_recall_checker_txt.py` — older standalone version, not used by the web app
- `templates/_nav.html` — shared two-level nav partial; included by all CRM pages
- `templates/home.html`, `accounts.html`, `account_form.html`, `leads.html`, `lead_form.html` — CRM pages
- `templates/index.html`, `status.html`, `dashboard.html`, `schedules.html`, `schedule_form.html` — recall checker pages
- `templates/notes.html` — shared scratchpad page (auto-save textarea bound to the `notepad` single-row table)
- `templates/mobile_keys.html`, `templates/mobile_key_form.html`, `templates/mobile_keys_inventory.html` — Key Database list, add/edit form, and Inventory list
- `supabase/schema.sql` — full base schema for setting up a NEW Supabase project
- `supabase/<date>_*.sql` — one file per migration; run on existing projects in chronological order
- `supabase/seed_mobile_keys.sql` — one-time INSERT seed for `mobile_keys` (the 14 historical rows from `Mocks/Key_DB.xlsx`, normalized to the official dropdowns). Run once after the `2026-05-12_mobile_keys.sql` migration. Not idempotent.
- `supabase/seed_mobile_keys_2026-04-15.sql` — second one-time INSERT seed (5 rows cut on 2026-04-15, hand-supplied). Same cleanup conventions as the first seed. Not idempotent.

## Supabase tables
- `schedules` — recurring recall checks. Optional `account_id` FK to `accounts`. `cadence` is one of `daily`/`monthly`/`quarterly` (the legacy `weekly` was dropped in the 2026-05-11 migration). `anchor_at` (nullable timestamptz) is the first-fire timestamp for monthly/quarterly rows; the scheduler builds an `IntervalTrigger` of 30 or 90 days starting at that anchor. Null `anchor_at` falls back to the legacy cron behavior (1st of the month, or 1st of Jan/Apr/Jul/Oct).
- `schedule_runs` — per-execution log (started_at, finished_at, recalls_found, email_sent, error)
- `notepad` — shared scratchpad behind `/notes`. Single-row table — a CHECK constraint pins `id = 1`, so `db.get_notepad()` / `db.save_notepad()` always read/write that one row. No history kept.
- `accounts` — master record for an existing customer (company, market, account_rep, fleet manager contact, service_type, VINs, notes). Supports an optional second fleet manager (`fleet_manager_2`, `fleet_manager_2_email`, `fleet_manager_2_phone`). Also stores origin context the same way leads do: `lead_source` ∈ `Sales`/`Service`/`Parts`/`Visual`/`Other` (nullable), `lead_source_other` (only when source is Other), `source_contact` (only for Sales/Service/Parts). The lead→account convert flow carries these over from the source lead. Check-in column: `last_checked_in_at` (timestamptz) + `check_in_note` (nullable text) — both editable from the accounts table cell. The cell opens a modal that lets the rep either save just a note (no date change, via `/accounts/<id>/check-in-note`) or check in (bump date + save note, via `/accounts/<id>/check-in`). When the cell is already green, only "Save note" is offered — re-check-in waits for the 25-day auto-flip (`ACCOUNT_CHECK_IN_DAYS = 25`). Note is never required and is shown in the cell's hover tooltip.
- `account_leads` — prospects (company, market, account_rep, phone, notes, optional `fleet_manager` / `fleet_manager_email` — collected for both lead types). Split into two workflows via `lead_type` (`cold` or `warm`); warm prospects additionally use `last_contacted_at`. `interest_level` (R/Y/G, default Y) still exists on the row but the lead form no longer collects it — new/edited leads fall back to `INTEREST_LEVEL_DEFAULT`. `lead_source` ∈ `Sales`/`Service`/`Parts`/`Visual`/`Other`; `source_contact` (free text) is only meaningful for Sales/Service/Parts and is cleared otherwise. Contact attempts are tracked on the row via `last_attempt_at` / `last_attempt_outcome` (`made_contact` or `left_voicemail`) / `last_attempt_note` — only the latest attempt is kept (no history table). `closed_at` + `closed_reason` soft-close a lead so it drops off the active list (mirrors how `converted_at` hides converted leads); `list_leads(include_converted=False)` filters out both converted and closed rows. `converted_at` + `converted_account_id` are set when a lead is converted.
- `mobile_keys` — one row per key cut. Columns: `cut_date`, `end_user` (`Internal`/`Customer`), `customer_name` (Internal = one of `KEY_INTERNAL_CUSTOMERS` = `Chevrolet, CDJR, Hyundai, Lincoln, Ford, Subaru, Toyota, Bid Lot`; Customer = free text), `ro_number`, `vin`, `year`, `make` (from `KEY_MAKES` ~21 brands), `model`, `key_type` (`Fob`/`Turnkey`/`Flip Key`), `key_fob_part_number`/`key_fob_cost`, `key_blank_part_number`/`key_blank_cost`, `programming_cost` (default `KEY_PROGRAMMING_COST_DEFAULT` = $60), `offset_eligible`, `moved_to_inventory_at` (nullable timestamptz — non-NULL means the part was moved to the Inventory page because the customer no longer needed it; the row still shows on the main Key Database list with the Inventory button filled), `status_done` (boolean, default false — toggled by the leftmost Status checkbox; pending rows render with a light-grey tint. The 2026-05-12 migration backfilled all pre-existing rows to true). Derived columns (Total Parts, Total Cost, Discount = `round(parts * KEY_DISCOUNT_RATE)`) are computed in `app.py` `_compute_key_totals()` at render time, not stored. Discount is `round(total_parts * 0.30)` to whole dollars to match the Excel formula.

`MARKETS` (and the `location`/`market` check constraints) use: Boyertown, Doylestown, Exton, Langhorne, Newtown, Washington, West Chester, Mechanicsburg, Company-Wide. The legacy value `GroupWide` was renamed to `Company-Wide` in the 2026-05-07 migration.

## Running Locally
```bash
pip install -r requirements.txt
python app.py
# or use run.bat
```

## Environment Variables
- `SUPABASE_URL`, `SUPABASE_KEY` — required; the app fails fast on first DB call without them.
- `RESEND_API_KEY` — API key for Resend email service
- `RESEND_FROM_EMAIL` — From address for email (default: `fordrecalls@voxapp.co`)
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

## Applying schema changes
- **New project:** paste `supabase/schema.sql` into the Supabase SQL Editor. End state matches all migrations applied in order.
- **Existing project:** run each `supabase/<date>_*.sql` file you haven't run yet, in chronological order. Each migration is self-contained — paste the whole file at once.
- After adding a new migration, also update `supabase/schema.sql` so a fresh setup arrives at the same end state.

## Deploying changes - Recall Checker
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
- One-time recall jobs run in background threads and results are stored in `outputs/`. Job state is in-memory only — restart loses the run log (the Supabase `schedule_runs` table only logs scheduled/manual runs of `schedules`, not ad-hoc one-time checks).
- `/submit` is rate-limited to 200 VINs per rolling 6 hours (`RATE_LIMIT_MAX_VINS`/`RATE_LIMIT_WINDOW` in `app.py`). The check is "is the window already full?" — submissions aren't capped by size, so a 400-VIN job goes through if the window had room, then locks out further submits until enough of those 400 ages past 6 hours. State is in-memory only (lost on restart) and scheduled runs are exempt.
- Single Gunicorn worker (see `gunicorn.conf.py`) keeps APScheduler to one instance — don't bump worker count without revisiting that.
- Selenium requires a compatible Chrome/Chromium + ChromeDriver setup (handled in the Dockerfile).
- The mobileservice@fredbeans.com address is auto-CC'd on every scheduled email; no need to add it to recipient lists.
- Account and lead create forms run a soft-duplicate check (`db.find_duplicate_matches`) against existing accounts + active leads on company name (case-insensitive exact), email (case-insensitive exact, sentinel `--` ignored), and phone (digits-only exact). On a match the form re-renders with a yellow warning banner; the user must resubmit with the hidden `confirm_duplicate=1` flag (set automatically by the "Save anyway" button) to bypass. Lead-to-account conversion excludes the source lead from its own duplicate set.
- The `/leads` page currently renders only warm prospects, grouped by account rep. The cold-call section is commented out in `templates/leads.html` (still present, just `{# ... #}`-wrapped) and the "+ New Lead" button defaults to `?type=warm`. Cold leads still exist in the DB and can be created via `/leads/new?type=cold` directly or by toggling the type radio on the form.
- Warm-prospect contact badges are color-coded by recency: green ≤19 days, yellow 20–29 days, red ≥30 days since `last_attempt_at`. The age (`days_since_contact`) is computed in `leads_list()` and rendered via the `recency_class` macro in the template.
- Schedule firing: daily uses a cron trigger at 6am ET; monthly/quarterly use `IntervalTrigger` (30/90 days) starting at `anchor_at`. On create, `_compute_anchor_at()` sets the anchor to today + 30 or 90 days at 6am ET. On edit, the anchor is only reset when the cadence itself changes — otherwise the existing anchor is preserved.
- The `/schedules/<id>/run` POST route (`schedule_run_now`) still exists, but the "Run Now" button on the schedules list was removed in the 2026-05-11 commit — the endpoint is no longer reachable from the UI.
