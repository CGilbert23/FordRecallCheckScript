import os
import sys
import uuid
import queue
import threading
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, request, render_template, jsonify, send_file, redirect, url_for
from recall_checker import process_recalls
import resend
import io
import openpyxl
import db
import scheduler
import dealership_locator as dealership_locator_mod

# Log everything to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.template_filter('format_money')
def _format_money(value):
    """Render a numeric value as '$1,234.56'. Blank/None becomes an em dash."""
    if value is None or value == '':
        return '—'
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return '—'


@app.template_filter('format_short_date')
def _format_short_date(value):
    """Render an ISO date string or date object as MM/DD/YY."""
    if value is None or value == '':
        return ''
    try:
        if isinstance(value, str):
            d = datetime.strptime(value[:10], '%Y-%m-%d').date()
        else:
            d = value
        return d.strftime('%m/%d/%y')
    except (ValueError, TypeError):
        return str(value)


resend.api_key = os.environ.get('RESEND_API_KEY', '')
RESEND_FROM_EMAIL = os.environ.get('RESEND_FROM_EMAIL', 'fordrecalls@voxapp.co')

# In-memory job store and queue
jobs = {}
job_queue = queue.Queue()

# Rolling-window rate limit on /submit. A submission is accepted as long as the
# 6-hour window had room when it arrived — but it's not capped by the limit, so
# a single 400-VIN job goes through and locks the window until enough of its
# VINs age past the 6-hour mark. Scheduled runs are exempt.
RATE_LIMIT_MAX_VINS = 200
RATE_LIMIT_WINDOW = timedelta(hours=6)
_rate_limit_entries = deque()  # (datetime, vin_count)
_rate_limit_lock = threading.Lock()


def _rate_limit_check_and_record(vin_count):
    """If the rolling window has room (current total < max), record this
    submission and return (True, None). Otherwise return (False, message)."""
    now = datetime.now()
    cutoff = now - RATE_LIMIT_WINDOW
    with _rate_limit_lock:
        while _rate_limit_entries and _rate_limit_entries[0][0] < cutoff:
            _rate_limit_entries.popleft()
        current = sum(c for _, c in _rate_limit_entries)
        if current >= RATE_LIMIT_MAX_VINS:
            running = 0
            unblock_at = None
            for ts, c in _rate_limit_entries:
                running += c
                if current - running < RATE_LIMIT_MAX_VINS:
                    unblock_at = ts + RATE_LIMIT_WINDOW
                    break
            # %-I is POSIX-only; fall back for Windows dev where it errors.
            try:
                when = unblock_at.strftime('%-I:%M %p') if unblock_at else 'soon'
            except ValueError:
                when = unblock_at.strftime('%I:%M %p').lstrip('0') if unblock_at else 'soon'
            msg = (
                f"Rate limit reached: {current} VINs submitted in the last "
                f"{int(RATE_LIMIT_WINDOW.total_seconds() // 3600)} hours "
                f"(limit {RATE_LIMIT_MAX_VINS}). Next slot opens at {when}."
            )
            return False, msg
        _rate_limit_entries.append((now, vin_count))
        return True, None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, 'outputs')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def parse_excel_upload(file_storage):
    """Parse uploaded Excel file. Returns (vins, vin_units).
    vin_units is a dict {vin: unit_number} if unit numbers found, else None.
    """
    wb = openpyxl.load_workbook(io.BytesIO(file_storage.read()), read_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return [], None

    # Auto-detect format: check if col B has VINs
    has_unit = False
    for row in rows:
        if len(row) >= 2 and row[1]:
            val = str(row[1]).strip()
            if len(val) == 17 and val.isalnum():
                has_unit = True
                break

    vins = []
    vin_units = {}

    for row in rows:
        if has_unit:
            if len(row) < 2 or not row[1]:
                continue
            unit = str(row[0]).strip() if row[0] else ''
            vin = str(row[1]).strip().upper()
            if not (len(vin) == 17 and vin.isalnum()):
                continue
            vins.append(vin)
            vin_units[vin] = unit
        else:
            if not row[0]:
                continue
            vin = str(row[0]).strip().upper()
            if not (len(vin) == 17 and vin.isalnum()):
                continue
            vins.append(vin)

    return vins, vin_units if has_unit else None


def queue_worker():
    """Worker thread that processes jobs one at a time from the queue."""
    while True:
        item = job_queue.get()
        job_id, vins, output_file, vin_units = item[:4]
        meta = item[4] if len(item) > 4 else None
        try:
            run_job(job_id, vins, output_file, vin_units, meta=meta)
        except Exception as e:
            logger.error(f"Queue worker error for job {job_id}: {str(e)}")
        finally:
            job_queue.task_done()


# Start the single worker thread
worker_thread = threading.Thread(target=queue_worker, daemon=True)
worker_thread.start()


ALWAYS_CC_EMAIL = 'mobileservice@fredbeans.com'


def enqueue_scheduled_run(schedule_id, triggered_by='scheduled'):
    """Load a schedule, log a run row, and enqueue the job for the worker.

    Called both by APScheduler (cron trigger) and the Run Now button.
    """
    schedule = db.get_schedule(schedule_id)
    if not schedule:
        logger.error(f"enqueue_scheduled_run: schedule {schedule_id} not found")
        return None

    vins = parse_vin_text(schedule.get('vins') or '')
    if not vins:
        logger.error(f"Schedule {schedule_id}: no valid VINs, skipping run")
        run = db.create_run(schedule_id, 0, triggered_by=triggered_by)
        if run:
            db.finish_run(run['id'], recalls_found=0, email_sent=False, error='No valid VINs in schedule')
        return None

    company = schedule['company_name']
    cadence = schedule['cadence']
    recipients = list(schedule.get('recipients') or [])
    subject = f"Automated Recall Check For {company}: {cadence.capitalize()}"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = ''.join(c for c in company if c.isalnum() or c in ' _-').strip().replace(' ', '_')
    filename = f'{safe_name or "Scheduled"}_{cadence}_{timestamp}.xlsx'
    output_file = os.path.join(OUTPUT_DIR, filename)

    run = db.create_run(schedule_id, len(vins), triggered_by=triggered_by)
    run_id = run['id'] if run else None

    job_id = uuid.uuid4().hex[:12]
    has_active = any(j['status'] in ('running', 'starting', 'queued') for j in jobs.values())
    initial_status = 'queued' if has_active else 'starting'

    jobs[job_id] = {
        'status': initial_status,
        'progress': {'current': 0, 'total': len(vins), 'status': initial_status},
        'output_file': output_file,
        'started': datetime.now().isoformat(),
        'vin_count': len(vins),
        'email': None,
        'name': f'{company} ({cadence})',
        'vin_units': None,
        'schedule_id': schedule_id,
        'triggered_by': triggered_by,
    }

    meta = {
        'subject': subject,
        'recipients': recipients,
        'schedule_run_id': run_id,
    }
    job_queue.put((job_id, vins, output_file, None, meta))
    logger.info(f"Enqueued schedule {schedule_id} ({triggered_by}) as job {job_id}")
    return job_id


# Start APScheduler once the app module is loaded. Single gunicorn worker
# (see gunicorn.conf.py) means exactly one scheduler instance, no dup fires.
try:
    scheduler.start(fire_callback=enqueue_scheduled_run)
except Exception as e:
    logger.error(f"Scheduler failed to start: {e}")


def parse_vin_text(text):
    """Parse a block of text into a list of valid 17-char alphanumeric VINs."""
    return [
        v.upper() for v in (line.strip() for line in text.splitlines() if line.strip())
        if len(v) == 17 and v.isalnum()
    ]


def format_phone(text):
    """Normalize a phone number to xxx-xxx-xxxx. Returns the original string
    unchanged if it doesn't contain a recognizable 10-digit US number."""
    if not text:
        return text
    digits = ''.join(c for c in text if c.isdigit())
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) == 10:
        return f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}"
    return text


def parse_recipients_text(text):
    """Parse recipients input (newline or comma separated) into a deduped list."""
    if not text:
        return []
    raw = text.replace(',', '\n').splitlines()
    seen = []
    for item in raw:
        e = item.strip()
        if e and e not in seen:
            seen.append(e)
    return seen


def _ensure_always_cc(recipients):
    """Return recipients with ALWAYS_CC_EMAIL appended if not already present."""
    lowered = {r.lower() for r in recipients}
    if ALWAYS_CC_EMAIL.lower() not in lowered:
        return list(recipients) + [ALWAYS_CC_EMAIL]
    return list(recipients)


def send_results_email(output_file, result, subject, recipients):
    """Send the Excel results file to the given recipients via Resend."""
    try:
        filename = os.path.basename(output_file)
        with open(output_file, 'rb') as f:
            file_content = list(f.read())

        with_recalls = result.get('with_recalls', 0)
        processed = result.get('processed', 0)

        to_list = _ensure_always_cc(recipients)

        resend.Emails.send({
            "from": RESEND_FROM_EMAIL,
            "to": to_list,
            "subject": subject,
            "html": (
                f"<h2>Ford Recall Check Complete</h2>"
                f"<p>Your recall check has finished processing.</p>"
                f"<ul>"
                f"<li><strong>VINs checked:</strong> {processed}</li>"
                f"<li><strong>Vehicles with recalls:</strong> {with_recalls}</li>"
                f"</ul>"
                f"<p>Your results are attached as an Excel file.</p>"
            ),
            "attachments": [{
                "filename": filename,
                "content": file_content,
            }],
        })
        logger.info(f"Results email sent to {to_list}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {recipients}: {str(e)}")
        return False


def run_job(job_id, vins, output_file, vin_units=None, meta=None):
    """Execute a recall check job. `meta` carries optional overrides:
        - subject: str — custom email subject
        - recipients: list[str] — recipient override (replaces the single `email` flow)
        - schedule_run_id: str — row in schedule_runs to finalize when done
    """
    meta = meta or {}

    def on_progress(data):
        jobs[job_id]['progress'] = data

    sent = None
    recalls_found = None
    error_msg = None

    is_scheduled = meta.get('schedule_run_id') is not None

    def _patch_one_time(**fields):
        """Best-effort update of the persisted one_time_runs row. Skipped for
        scheduled jobs (they're tracked in schedule_runs instead)."""
        if is_scheduled:
            return
        try:
            db.update_one_time_run(job_id, **fields)
        except Exception as e:
            logger.error(f"Failed to update one_time_run for job {job_id}: {e}")

    try:
        logger.info(f"Job {job_id}: starting with {len(vins)} VINs")
        jobs[job_id]['status'] = 'running'
        _patch_one_time(status='running')
        result = process_recalls(vins, output_file, progress_callback=on_progress, vin_units=vin_units)
        jobs[job_id]['status'] = 'complete'
        jobs[job_id]['result'] = result
        jobs[job_id]['output_file'] = output_file
        recalls_found = result.get('with_recalls', 0)
        logger.info(f"Job {job_id}: complete - {recalls_found} recalls found")

        if is_scheduled:
            # Scheduled runs always send email (always-CC handles empty recipient lists).
            subject = meta.get('subject') or f"Ford Recall Results - {recalls_found} recall(s) found"
            recipients = meta.get('recipients') or []
            sent = send_results_email(output_file, result, subject, recipients)
        else:
            email = jobs[job_id].get('email')
            if email:
                subject = f"Ford Recall Results - {recalls_found} recall(s) found"
                sent = send_results_email(output_file, result, subject, [email])
        if sent is not None:
            jobs[job_id]['email_sent'] = sent
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Job {job_id}: FAILED - {error_msg}")
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['error'] = error_msg
    finally:
        run_id = meta.get('schedule_run_id')
        if run_id:
            try:
                db.finish_run(run_id, recalls_found=recalls_found, email_sent=bool(sent), error=error_msg)
            except Exception as e:
                logger.error(f"Failed to finalize schedule_run {run_id}: {e}")
        else:
            final_status = jobs[job_id]['status']
            _patch_one_time(
                status=final_status,
                finished_at=datetime.now(timezone.utc).isoformat(),
                recalls_found=recalls_found,
                email_sent=sent,
                error=error_msg,
            )


@app.route('/test-chrome')
def test_chrome():
    """Test if Chrome can start in this environment"""
    import shutil
    info = {
        'chrome_bin_env': os.environ.get('CHROME_BIN', 'not set'),
        'chromium_exists': os.path.exists('/usr/bin/chromium'),
        'chromedriver_path': shutil.which('chromedriver'),
    }
    try:
        from recall_checker import setup_driver
        logger.info("Testing Chrome startup...")
        driver = setup_driver()
        driver.get('https://www.google.com')
        info['title'] = driver.title
        info['status'] = 'Chrome works!'
        driver.quit()
    except Exception as e:
        info['status'] = f'FAILED: {str(e)}'
        logger.error(f"Chrome test failed: {str(e)}")
    return jsonify(info)


@app.route('/test-supabase')
def test_supabase():
    """Verify Supabase connection and that schedules table is reachable."""
    try:
        return jsonify(db.ping())
    except Exception as e:
        logger.error(f"Supabase ping failed: {str(e)}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/')
def home():
    return render_template('home.html')


@app.route('/used-car-tracker')
def used_car_tracker():
    return render_template('used_car_tracker.html')


@app.route('/dealership-locator', methods=['GET', 'POST'])
def dealership_locator():
    """Rank the 7 Fred Beans Ford stores by driving distance from a user-entered
    address/town/ZIP. Form posts back to this route and renders results inline."""
    if request.method == 'POST':
        search_type = (request.form.get('search_type') or 'zip').strip().lower()
        if search_type not in ('zip', 'city', 'address'):
            search_type = 'zip'
        query = (request.form.get('query') or '').strip()
        if not query:
            return render_template('dealership_locator.html', query='', search_type=search_type,
                                   error='Enter a value to search.')
        if search_type == 'zip' and not (query.isdigit() and len(query) == 5):
            return render_template('dealership_locator.html', query=query, search_type=search_type,
                                   error='ZIP must be 5 digits.')
        result = dealership_locator_mod.find_nearest(query)
        if result.get('error'):
            return render_template('dealership_locator.html', query=query, search_type=search_type,
                                   error=result['error'])
        return render_template('dealership_locator.html', query=query, search_type=search_type,
                               results=result['results'], origin=result['origin'])
    return render_template('dealership_locator.html', query='', search_type='zip')


@app.route('/recall-checker')
def one_time_form():
    active = sum(1 for j in jobs.values() if j['status'] in ('running', 'starting', 'queued'))
    prefill = {}
    account_id = (request.args.get('account_id') or '').strip()
    if account_id:
        try:
            account = db.get_account(account_id)
            if account:
                prefill = {
                    'vins': account.get('vins') or '',
                    'name': account.get('company_name') or '',
                }
        except Exception as e:
            logger.error(f"Failed to prefill one-time form from account {account_id}: {e}")
    return render_template('index.html', active_jobs=active, prefill=prefill)


@app.route('/submit', methods=['POST'])
def submit():
    logger.info("Submit received")

    excel_file = request.files.get('excel_file')
    if excel_file and excel_file.filename:
        vins, vin_units = parse_excel_upload(excel_file)
    else:
        text = request.form.get('vins', '')
        vins = [v.upper() for v in (line.strip() for line in text.splitlines() if line.strip()) if len(v) == 17 and v.isalnum()]
        vin_units = None

    logger.info(f"Parsed {len(vins)} valid VINs")

    if not vins:
        active = sum(1 for j in jobs.values() if j['status'] in ('running', 'starting', 'queued'))
        return render_template('index.html', active_jobs=active, error='No valid VINs found. Each VIN must be exactly 17 alphanumeric characters.')

    allowed, rate_msg = _rate_limit_check_and_record(len(vins))
    if not allowed:
        active = sum(1 for j in jobs.values() if j['status'] in ('running', 'starting', 'queued'))
        logger.warning(f"Submit blocked by rate limit: {rate_msg}")
        return render_template('index.html', active_jobs=active, error=rate_msg)

    email = request.form.get('email', '').strip()
    name = request.form.get('name', '').strip()

    job_id = uuid.uuid4().hex[:12]
    date_str = datetime.now().strftime("%m_%d_%Y")
    safe_name = ''.join(c for c in name if c.isalnum() or c in ' _-').strip().replace(' ', '_')
    if safe_name:
        filename = f'{safe_name}_FordRecalls_{date_str}.xlsx'
    else:
        filename = f'FordRecalls_{date_str}.xlsx'
    output_file = os.path.join(OUTPUT_DIR, filename)

    # Check if another job is already running/queued
    has_active = any(j['status'] in ('running', 'starting', 'queued') for j in jobs.values())
    initial_status = 'queued' if has_active else 'starting'

    jobs[job_id] = {
        'status': initial_status,
        'progress': {'current': 0, 'total': len(vins), 'status': initial_status},
        'output_file': output_file,
        'started': datetime.now().isoformat(),
        'vin_count': len(vins),
        'email': email or None,
        'name': name or None,
        'vin_units': vin_units,
    }

    logger.info(f"Created job {job_id} (status: {initial_status})")

    try:
        db.create_one_time_run(
            job_id=job_id,
            vins=vins,
            status=initial_status,
            customer_name=name or None,
            output_file=output_file,
            email=email or None,
        )
    except Exception as e:
        # Persisting the run is best-effort — if Supabase is down we still
        # want the in-memory job to run. The run just won't appear in the log.
        logger.error(f"Failed to persist one_time_run for job {job_id}: {e}")

    job_queue.put((job_id, vins, output_file, vin_units))

    return redirect(url_for('job_page', job_id=job_id))


@app.route('/job/<job_id>')
def job_page(job_id):
    if job_id not in jobs:
        logger.warning(f"Job page requested for unknown job {job_id}")
        return render_template('status.html', job_id=job_id, job={
            'status': 'error',
            'error': 'Job not found. The server may have restarted. Please go back and try again.',
            'vin_count': 0,
            'progress': {'current': 0, 'total': 0},
        })
    return render_template('status.html', job_id=job_id, job=jobs[job_id])


@app.route('/status/<job_id>')
def status(job_id):
    if job_id not in jobs:
        return jsonify({'status': 'error', 'error': 'Job not found. The server may have restarted. Please go back and try again.', 'progress': {'current': 0, 'total': 0}})
    return jsonify(jobs[job_id])


@app.route('/recall/run-log')
def run_log():
    try:
        rows = db.list_one_time_runs(limit=200)
    except Exception as e:
        logger.error(f"Failed to load one_time_runs: {e}")
        rows = []
    return render_template('dashboard.html', runs=rows)


@app.route('/dashboard')
def dashboard_redirect():
    return redirect(url_for('run_log'))


@app.route('/schedules')
def schedules_list():
    try:
        rows = db.list_schedules()
    except Exception as e:
        logger.error(f"Failed to load schedules: {e}")
        rows = []

    for r in rows:
        r['vin_count'] = len(parse_vin_text(r.get('vins') or ''))
        r['last_run'] = None
        r['last_run_email_sent'] = None
        r['last_run_error'] = None
        r['next_run'] = None
        try:
            recent = db.list_runs(r['id'], limit=1)
            if recent:
                run = recent[0]
                started = run.get('started_at') or ''
                r['last_run'] = started[:16].replace('T', ' ') if started else None
                r['last_run_email_sent'] = run.get('email_sent')
                r['last_run_error'] = run.get('error')
        except Exception as e:
            logger.error(f"Failed to load runs for {r['id']}: {e}")
        try:
            nrt = scheduler.next_run_time(r['id'])
            if nrt is not None:
                # Date-only "MM/DD/YYYY". All scheduled runs fire at 6am ET so
                # the time portion isn't useful day-to-day.
                r['next_run'] = nrt.strftime('%m/%d/%Y')
        except Exception as e:
            logger.error(f"Failed to read next run time for {r['id']}: {e}")

    return render_template(
        'schedules.html',
        schedules=rows,
        locations=db.LOCATIONS,
    )


_SCHEDULE_ANCHOR_OFFSET_DAYS = {'monthly': 30, 'quarterly': 90}


def _compute_anchor_at(cadence):
    """First-fire timestamp for monthly/quarterly schedules: today + 30 or 90
    days, at 6:00 AM Eastern. Daily schedules don't need an anchor (cron handles
    them), so this returns None for anything outside the offset map."""
    offset = _SCHEDULE_ANCHOR_OFFSET_DAYS.get(cadence)
    if offset is None:
        return None
    et = datetime.now(scheduler.TZ)
    first_fire = et.replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=offset)
    return first_fire.isoformat()


@app.route('/schedules/new', methods=['GET', 'POST'])
def schedule_new():
    """Account-only creation. Requires ?account_id=X on GET; on POST, the
    account_id field on the form determines the schedule's locked fields
    (company/market/vins are re-derived from the account, ignoring submitted
    values so a tampered form can't drift the schedule from its account)."""
    if request.method == 'POST':
        account_id = (request.form.get('account_id') or '').strip()
        account = db.get_account(account_id) if account_id else None
        if not account:
            return redirect(url_for('accounts_list'))

        form, error = _read_schedule_form(request, locked_account=account)
        if error:
            return render_template(
                'schedule_form.html', schedule=None, form=form, error=error,
                cadences=db.CADENCES, account_locked=account,
            )
        try:
            created = db.create_schedule({
                'company_name': account['company_name'],
                'location': account['market'],
                'cadence': form['cadence'],
                'vins': account.get('vins') or '',
                'recipients': form['recipients'],
                'active': True,
                'account_id': account['id'],
                'anchor_at': _compute_anchor_at(form['cadence']),
            })
            if created:
                scheduler.register(created)
        except Exception as e:
            logger.error(f"Create schedule failed: {e}")
            return render_template(
                'schedule_form.html', schedule=None, form=form, error=str(e),
                cadences=db.CADENCES, account_locked=account,
            )
        return redirect(url_for('schedules_list'))

    # GET: must arrive with ?account_id=...
    account_id = (request.args.get('account_id') or '').strip()
    account = db.get_account(account_id) if account_id else None
    if not account:
        return redirect(url_for('accounts_list'))

    rep_email = db.ACCOUNT_REP_EMAILS.get(account.get('account_rep'))
    form = {
        'company_name': account['company_name'],
        'location': account['market'],
        'vins': account.get('vins') or '',
        'cadence': '',
        'recipients_text': rep_email or '',
        'active': True,
        'account_id': account['id'],
    }
    return render_template(
        'schedule_form.html', schedule=None, form=form,
        cadences=db.CADENCES, account_locked=account,
    )


@app.route('/schedules/<schedule_id>/edit', methods=['GET', 'POST'])
def schedule_edit(schedule_id):
    existing = db.get_schedule(schedule_id)
    if not existing:
        return 'Schedule not found', 404

    # Schedules created post-rebuild always have an account_id. Hydrate the
    # locked fields from the linked account so they always reflect the latest.
    account = db.get_account(existing['account_id']) if existing.get('account_id') else None

    if request.method == 'POST':
        form, error = _read_schedule_form(request, include_active=True, locked_account=account)
        if error:
            form['id'] = schedule_id
            return render_template(
                'schedule_form.html', schedule=existing, form=form, error=error,
                cadences=db.CADENCES, account_locked=account,
            )
        try:
            payload = {
                'cadence': form['cadence'],
                'recipients': form['recipients'],
                'active': form['active'],
            }
            # When the cadence changes, reset the anchor so the new cadence
            # starts a fresh 30/90-day window from "now". Leaving cadence
            # alone keeps the existing anchor (and legacy null-anchor rows
            # remain on cron-on-the-1st).
            if form['cadence'] != existing.get('cadence'):
                payload['anchor_at'] = _compute_anchor_at(form['cadence'])
            if account:
                payload['company_name'] = account['company_name']
                payload['location'] = account['market']
                payload['vins'] = account.get('vins') or ''
            updated = db.update_schedule(schedule_id, payload)
            if updated:
                if updated.get('active'):
                    scheduler.register(updated)
                else:
                    scheduler.unregister(schedule_id)
        except Exception as e:
            logger.error(f"Update schedule failed: {e}")
            return render_template(
                'schedule_form.html', schedule=existing, form=form, error=str(e),
                cadences=db.CADENCES, account_locked=account,
            )
        return redirect(url_for('schedules_list'))

    form = {
        'company_name': (account or existing).get('company_name') or '',
        'location': (account.get('market') if account else existing.get('location')) or '',
        'cadence': existing['cadence'],
        'vins': (account.get('vins') if account else existing.get('vins')) or '',
        'recipients_text': '\n'.join(existing.get('recipients') or []),
        'active': existing.get('active', True),
        'account_id': existing.get('account_id'),
    }
    return render_template(
        'schedule_form.html', schedule=existing, form=form,
        cadences=db.CADENCES, account_locked=account,
    )


@app.route('/schedules/<schedule_id>/delete', methods=['POST'])
def schedule_delete(schedule_id):
    try:
        scheduler.unregister(schedule_id)
        db.delete_schedule(schedule_id)
    except Exception as e:
        logger.error(f"Delete schedule failed: {e}")
    return redirect(url_for('schedules_list'))


@app.route('/schedules/<schedule_id>/run', methods=['POST'])
def schedule_run_now(schedule_id):
    try:
        enqueue_scheduled_run(schedule_id, triggered_by='manual')
    except Exception as e:
        logger.error(f"Run Now failed for {schedule_id}: {e}")
    return redirect(url_for('schedules_list'))


def _read_schedule_form(req, include_active=False, locked_account=None):
    """Validate a schedules form submission. Returns (form_dict, error_or_none).

    When `locked_account` is provided, company/market/VINs are pulled from the
    account record and the corresponding form fields are ignored (visual locks
    only). Cadence and recipients are still required.
    """
    cadence = req.form.get('cadence', '').strip()
    recipients_raw = req.form.get('recipients', '')
    active = bool(req.form.get('active')) if include_active else True
    account_id = req.form.get('account_id', '').strip() or None

    recipients = parse_recipients_text(recipients_raw)

    if locked_account:
        company_name = locked_account['company_name']
        location = locked_account['market']
        vins_raw = locked_account.get('vins') or ''
    else:
        company_name = req.form.get('company_name', '').strip()
        location = req.form.get('location', '').strip()
        vins_raw = req.form.get('vins', '')

    vins = parse_vin_text(vins_raw)

    form = {
        'company_name': company_name,
        'location': location,
        'cadence': cadence,
        'vins': '\n'.join(vins),
        'recipients': recipients,
        'recipients_text': recipients_raw,
        'active': active,
        'account_id': account_id,
    }

    if not company_name:
        return form, 'Company name is required.'
    if location not in db.LOCATIONS:
        return form, 'Please pick a valid location.'
    if cadence not in db.CADENCES:
        return form, 'Please pick a valid cadence.'
    if not vins:
        return form, 'No valid VINs on the linked account. Add VINs to the account before scheduling.'

    return form, None


@app.route('/download/<job_id>')
def download(job_id):
    if job_id not in jobs:
        return 'Job not found', 404
    job = jobs[job_id]
    if job['status'] != 'complete' or not os.path.exists(job.get('output_file', '')):
        return 'File not ready', 400
    return send_file(job['output_file'], as_attachment=True, download_name=os.path.basename(job['output_file']))


# ---------------------------------------------------------------------------
# CRM: Accounts
# ---------------------------------------------------------------------------

def _safe_list_accounts():
    try:
        return db.list_accounts()
    except Exception as e:
        logger.error(f"Failed to list accounts: {e}")
        return []


def _read_account_form(req):
    """Validate the account form. Returns (form_dict, error_or_none)."""
    company_name = req.form.get('company_name', '').strip()
    market = req.form.get('market', '').strip()
    account_rep = req.form.get('account_rep', '').strip()
    fleet_manager = req.form.get('fleet_manager', '').strip()
    fleet_manager_email = req.form.get('fleet_manager_email', '').strip()
    fleet_manager_phone = format_phone(req.form.get('fleet_manager_phone', '').strip())
    fleet_manager_2 = req.form.get('fleet_manager_2', '').strip()
    fleet_manager_2_email = req.form.get('fleet_manager_2_email', '').strip()
    fleet_manager_2_phone = format_phone(req.form.get('fleet_manager_2_phone', '').strip())
    service_type = req.form.get('service_type', '').strip()
    vins_raw = req.form.get('vins', '').strip()
    notes = req.form.get('notes', '').strip()

    vin_list = parse_vin_text(vins_raw)
    vins_normalized = '\n'.join(vin_list)

    form = {
        'company_name': company_name,
        'market': market,
        'account_rep': account_rep,
        'fleet_manager': fleet_manager,
        'fleet_manager_email': fleet_manager_email,
        'fleet_manager_phone': fleet_manager_phone,
        'fleet_manager_2': fleet_manager_2,
        'fleet_manager_2_email': fleet_manager_2_email,
        'fleet_manager_2_phone': fleet_manager_2_phone,
        'service_type': service_type,
        'vins': vins_normalized,
        'vin_count': len(vin_list),
        'notes': notes,
    }

    if not company_name:
        return form, 'Company name is required.'
    if market not in db.MARKETS:
        return form, 'Please pick a valid market.'
    if account_rep not in db.ACCOUNT_REPS:
        return form, 'Please pick a valid account representative.'
    if service_type not in db.SERVICE_TYPES:
        return form, 'Please pick a service type.'
    return form, None


def _account_payload(form):
    return {
        'company_name': form['company_name'],
        'market': form['market'],
        'account_rep': form['account_rep'],
        'fleet_manager': form['fleet_manager'] or None,
        'fleet_manager_email': form['fleet_manager_email'] or '--',
        'fleet_manager_phone': form['fleet_manager_phone'] or '--',
        'fleet_manager_2': form['fleet_manager_2'] or None,
        'fleet_manager_2_email': form['fleet_manager_2_email'] or None,
        'fleet_manager_2_phone': form['fleet_manager_2_phone'] or None,
        'service_type': form['service_type'],
        'vins': form['vins'] or None,
        'notes': form['notes'] or None,
    }


@app.route('/accounts')
def accounts_list():
    try:
        grouped = db.list_accounts_grouped_by_rep()
    except Exception as e:
        logger.error(f"Failed to load accounts: {e}")
        grouped = {rep: [] for rep in db.ACCOUNT_REPS}

    schedules_by_account = {}
    try:
        for s in db.list_schedules():
            aid = s.get('account_id')
            if aid:
                schedules_by_account.setdefault(aid, []).append(s)
    except Exception as e:
        logger.error(f"Failed to load schedules for accounts page: {e}")

    for accounts in grouped.values():
        for acct in accounts:
            acct['vin_count'] = len(parse_vin_text(acct.get('vins') or ''))

    return render_template(
        'accounts.html',
        grouped=grouped,
        reps=db.ACCOUNT_REPS,
        markets=db.MARKETS,
        schedules_by_account=schedules_by_account,
    )


@app.route('/accounts/new', methods=['GET', 'POST'])
def account_new():
    if request.method == 'POST':
        form, error = _read_account_form(request)
        from_lead_id = (request.form.get('from_lead_id') or '').strip() or None
        confirm_duplicate = request.form.get('confirm_duplicate') == '1'
        if error:
            return render_template(
                'account_form.html', account=None, form=form, error=error,
                markets=db.MARKETS, reps=db.ACCOUNT_REPS, service_types=db.SERVICE_TYPES,
                from_lead_id=from_lead_id,
            )
        if not confirm_duplicate:
            try:
                duplicates = db.find_duplicate_matches(
                    company_name=form['company_name'],
                    emails=[form.get('fleet_manager_email'), form.get('fleet_manager_2_email')],
                    phones=[form.get('fleet_manager_phone'), form.get('fleet_manager_2_phone')],
                )
            except Exception as e:
                logger.error(f"Duplicate check failed (account create): {e}")
                duplicates = []
            # When converting a lead, the source lead itself isn't a duplicate.
            if from_lead_id:
                duplicates = [d for d in duplicates if not (d['table'] == 'leads' and d['id'] == from_lead_id)]
            if duplicates:
                return render_template(
                    'account_form.html', account=None, form=form, error=None,
                    markets=db.MARKETS, reps=db.ACCOUNT_REPS, service_types=db.SERVICE_TYPES,
                        from_lead_id=from_lead_id, duplicates=duplicates,
                )
        try:
            if from_lead_id:
                created = db.convert_lead_to_account(from_lead_id, _account_payload(form))
            else:
                created = db.create_account(_account_payload(form))
            if not created:
                raise RuntimeError('Account create returned no row')
        except Exception as e:
            logger.error(f"Create account failed: {e}")
            return render_template(
                'account_form.html', account=None, form=form, error=str(e),
                markets=db.MARKETS, reps=db.ACCOUNT_REPS, service_types=db.SERVICE_TYPES,
                from_lead_id=from_lead_id,
            )
        return redirect(url_for('accounts_list'))

    return render_template(
        'account_form.html', account=None, form={},
        markets=db.MARKETS, reps=db.ACCOUNT_REPS, service_types=db.SERVICE_TYPES,
        from_lead_id=None,
    )


@app.route('/accounts/<account_id>/edit', methods=['GET', 'POST'])
def account_edit(account_id):
    try:
        existing = db.get_account(account_id)
    except Exception as e:
        logger.error(f"Failed to load account {account_id}: {e}")
        existing = None
    if not existing:
        return 'Account not found', 404

    if request.method == 'POST':
        form, error = _read_account_form(request)
        if error:
            return render_template(
                'account_form.html', account=existing, form=form, error=error,
                markets=db.MARKETS, reps=db.ACCOUNT_REPS, service_types=db.SERVICE_TYPES,
                from_lead_id=None,
            )
        try:
            payload = _account_payload(form)
            db.update_account(account_id, payload)
            # Keep linked schedules' VIN list in sync. Account is the source
            # of truth; schedules just snapshot it on save so the next run
            # picks up the new fleet.
            new_vins = payload.get('vins') or ''
            if (existing.get('vins') or '') != new_vins:
                for s in db.list_schedules_for_account(account_id):
                    try:
                        db.update_schedule(s['id'], {'vins': new_vins})
                    except Exception as sync_err:
                        logger.error(f"Failed to sync VINs to schedule {s['id']}: {sync_err}")
        except Exception as e:
            logger.error(f"Update account failed: {e}")
            return render_template(
                'account_form.html', account=existing, form=form, error=str(e),
                markets=db.MARKETS, reps=db.ACCOUNT_REPS, service_types=db.SERVICE_TYPES,
                from_lead_id=None,
            )
        return redirect(url_for('accounts_list'))

    form = {
        'company_name': existing.get('company_name') or '',
        'market': existing.get('market') or '',
        'account_rep': existing.get('account_rep') or '',
        'fleet_manager': existing.get('fleet_manager') or '',
        'fleet_manager_email': (existing.get('fleet_manager_email') or '').replace('--', ''),
        'fleet_manager_phone': (existing.get('fleet_manager_phone') or '').replace('--', ''),
        'fleet_manager_2': existing.get('fleet_manager_2') or '',
        'fleet_manager_2_email': existing.get('fleet_manager_2_email') or '',
        'fleet_manager_2_phone': existing.get('fleet_manager_2_phone') or '',
        'service_type': existing.get('service_type') or '',
        'vins': existing.get('vins') or '',
        'vin_count': len(parse_vin_text(existing.get('vins') or '')),
        'notes': existing.get('notes') or '',
    }
    return render_template(
        'account_form.html', account=existing, form=form,
        markets=db.MARKETS, reps=db.ACCOUNT_REPS, service_types=db.SERVICE_TYPES,
        from_lead_id=None,
    )


@app.route('/accounts/<account_id>/delete', methods=['POST'])
def account_delete(account_id):
    try:
        # Cascade-delete linked schedules so they don't become orphaned (they
        # have no edit path once their account is gone, since schedules are
        # only created from accounts).
        for s in db.list_schedules_for_account(account_id):
            try:
                scheduler.unregister(s['id'])
            except Exception as sched_err:
                logger.error(f"Failed to unregister schedule {s['id']}: {sched_err}")
            try:
                db.delete_schedule(s['id'])
            except Exception as del_err:
                logger.error(f"Failed to delete schedule {s['id']}: {del_err}")
        db.delete_account(account_id)
    except Exception as e:
        logger.error(f"Delete account failed: {e}")
    return redirect(url_for('accounts_list'))


# ---------------------------------------------------------------------------
# Mobile Keys (Key Database)
# ---------------------------------------------------------------------------

def _key_year_range():
    """Years for the form dropdown. Extends to next year each January."""
    current = datetime.now().year
    upper = max(2026, current + 1)
    return list(range(upper, 1999, -1))  # descending, newest first


def _parse_money(raw):
    """Parse a money-ish form value. Returns (float_or_None, error).

    Accepts blank (None), bare numbers, and '$1,234.56'-style strings. The
    Excel uses '--' for missing parts costs — treat that the same as blank.
    """
    if raw is None:
        return None, None
    s = str(raw).strip()
    if s == '' or s == '--' or s == '-':
        return None, None
    cleaned = s.replace('$', '').replace(',', '').strip()
    try:
        return float(cleaned), None
    except ValueError:
        return None, f"Invalid money value: {raw!r}"


def _compute_key_totals(row):
    """Attach derived totals to a mobile_keys row dict for display."""
    fob = float(row.get('key_fob_cost') or 0)
    blank = float(row.get('key_blank_cost') or 0)
    programming = float(row.get('programming_cost') or 0)
    parts_total = fob + blank
    # Billed Total = parts + parts markup + programming. Markup depends on who's
    # billed: Internal 10%, Customer 35%.
    markup_rate = (db.KEY_MARKUP_CUSTOMER if row.get('end_user') == 'Customer'
                   else db.KEY_MARKUP_INTERNAL)
    row['total_parts_cost'] = parts_total
    row['total_cost'] = parts_total * (1 + markup_rate) + programming
    # Internal keys may carry a person (car already sold, key cut at their
    # house). Shown as "FB Chevrolet - Mark Macy"; blank falls back to the store.
    contact = (row.get('internal_contact') or '').strip()
    name = row.get('customer_name') or ''
    row['customer_display'] = f"{name} - {contact}" if contact else name
    return row


def _parse_mobile_key_form(req):
    """Read + validate the mobile-key form. Returns (form, error, payload).

    `form` always holds the raw inputs so the template can re-render on
    validation failure without losing what the rep typed. On success
    `error` is None and `payload` is the dict ready for the DB; on failure
    `error` is the message and `payload` is None.
    """
    form = {
        'cut_date': (req.form.get('cut_date') or '').strip(),
        'end_user': (req.form.get('end_user') or '').strip(),
        'customer_name_internal': (req.form.get('customer_name_internal') or '').strip(),
        'customer_name_external': (req.form.get('customer_name_external') or '').strip(),
        'internal_contact': (req.form.get('internal_contact') or '').strip(),
        'ro_number': (req.form.get('ro_number') or '').strip(),
        'vin': (req.form.get('vin') or '').strip().upper(),
        'year': (req.form.get('year') or '').strip(),
        'make': (req.form.get('make') or '').strip(),
        'model': (req.form.get('model') or '').strip(),
        'key_type': (req.form.get('key_type') or '').strip(),
        'key_fob_part_number': (req.form.get('key_fob_part_number') or '').strip(),
        'key_fob_cost': (req.form.get('key_fob_cost') or '').strip(),
        'key_blank_part_number': (req.form.get('key_blank_part_number') or '').strip(),
        'key_blank_cost': (req.form.get('key_blank_cost') or '').strip(),
        'programming_cost': (req.form.get('programming_cost') or '').strip(),
        'offset_eligible': req.form.get('offset_eligible', 'Y'),
        'notes': (req.form.get('notes') or '').strip(),
    }

    # Appt Date is optional — reps may log a key before it's scheduled.
    if form['cut_date']:
        try:
            cut_date = datetime.strptime(form['cut_date'], '%Y-%m-%d').date()
        except ValueError:
            return form, 'Appt Date must be a valid date.', None
    else:
        cut_date = None

    if form['end_user'] not in db.KEY_END_USERS:
        return form, 'End User must be Internal or Customer.', None

    if form['end_user'] == 'Internal':
        customer_name = form['customer_name_internal']
        if customer_name not in db.KEY_INTERNAL_CUSTOMERS:
            return form, 'Pick an internal customer from the list.', None
        # Optional free text — the person we're meeting when the car was sold.
        internal_contact = form['internal_contact']
    else:
        customer_name = form['customer_name_external']
        if not customer_name:
            return form, 'Customer Name is required.', None
        # Internal-only field; drop any stale value when billing flips.
        internal_contact = ''

    if len(form['vin']) != 17 or not form['vin'].isalnum():
        return form, 'VIN must be exactly 17 alphanumeric characters.', None

    try:
        year = int(form['year'])
    except (TypeError, ValueError):
        return form, 'Year is required.', None
    if year < 2000 or year > 2100:
        return form, 'Year is out of range.', None

    if form['make'] not in db.KEY_MAKES:
        return form, 'Pick a Make from the list.', None
    if not form['model']:
        return form, 'Model is required.', None
    if form['key_type'] not in db.KEY_TYPES:
        return form, 'Pick a Key Type from the list.', None

    fob_cost, err = _parse_money(form['key_fob_cost'])
    if err:
        return form, err, None
    blank_cost, err = _parse_money(form['key_blank_cost'])
    if err:
        return form, err, None
    programming_cost, err = _parse_money(form['programming_cost'])
    if err:
        return form, err, None
    if programming_cost is None:
        programming_cost = db.KEY_PROGRAMMING_COST_DEFAULT

    fob_part = form['key_fob_part_number']
    if fob_part in ('--', '-'):
        fob_part = ''
    blank_part = form['key_blank_part_number']
    if blank_part in ('--', '-'):
        blank_part = ''
    ro_number = form['ro_number']
    if ro_number in ('--', '-'):
        ro_number = ''

    payload = {
        'cut_date': cut_date.isoformat() if cut_date else None,
        'end_user': form['end_user'],
        'customer_name': customer_name,
        'internal_contact': internal_contact or None,
        'ro_number': ro_number or None,
        'vin': form['vin'],
        'year': year,
        'make': form['make'],
        'model': form['model'],
        'key_type': form['key_type'],
        'key_fob_part_number': fob_part or None,
        'key_fob_cost': fob_cost,
        'key_blank_part_number': blank_part or None,
        'key_blank_cost': blank_cost,
        'programming_cost': programming_cost,
        'offset_eligible': form['offset_eligible'] == 'Y',
        'notes': form['notes'] or None,
    }
    return form, None, payload


def _mobile_key_form_context(form=None, key=None, error=None):
    return dict(
        form=form or {},
        key=key,
        error=error,
        years=_key_year_range(),
        internal_customers=db.KEY_INTERNAL_CUSTOMERS,
        makes=db.KEY_MAKES,
        key_types=db.KEY_TYPES,
        end_users=db.KEY_END_USERS,
        programming_default=db.KEY_PROGRAMMING_COST_DEFAULT,
    )


@app.route('/mobile-keys')
def mobile_keys_list():
    try:
        rows = db.list_mobile_keys()
    except Exception as e:
        logger.error(f"Failed to list mobile keys: {e}")
        rows = []
    for r in rows:
        _compute_key_totals(r)
    return render_template('mobile_keys.html', keys=rows)


@app.route('/mobile-keys/new', methods=['GET', 'POST'])
def mobile_key_new():
    if request.method == 'POST':
        form, error, payload = _parse_mobile_key_form(request)
        if error:
            return render_template(
                'mobile_key_form.html',
                **_mobile_key_form_context(form=form, error=error),
            )
        try:
            db.create_mobile_key(payload)
        except Exception as e:
            logger.error(f"Create mobile key failed: {e}")
            return render_template(
                'mobile_key_form.html',
                **_mobile_key_form_context(form=form, error=str(e)),
            )
        return redirect(url_for('mobile_keys_list'))

    # GET: prefill with sensible defaults
    today = datetime.now().date().isoformat()
    form = {
        'cut_date': today,
        'end_user': 'Internal',
        'programming_cost': f"{db.KEY_PROGRAMMING_COST_DEFAULT:.2f}",
        'offset_eligible': 'Y',
    }
    return render_template(
        'mobile_key_form.html',
        **_mobile_key_form_context(form=form),
    )


@app.route('/mobile-keys/<key_id>/edit', methods=['GET', 'POST'])
def mobile_key_edit(key_id):
    try:
        existing = db.get_mobile_key(key_id)
    except Exception as e:
        logger.error(f"Failed to load mobile key {key_id}: {e}")
        existing = None
    if not existing:
        return 'Key record not found', 404

    if request.method == 'POST':
        form, error, payload = _parse_mobile_key_form(request)
        if error:
            return render_template(
                'mobile_key_form.html',
                **_mobile_key_form_context(form=form, key=existing, error=error),
            )
        try:
            db.update_mobile_key(key_id, payload)
        except Exception as e:
            logger.error(f"Update mobile key failed: {e}")
            return render_template(
                'mobile_key_form.html',
                **_mobile_key_form_context(form=form, key=existing, error=str(e)),
            )
        return redirect(url_for('mobile_keys_list'))

    is_internal = existing.get('end_user') == 'Internal'
    form = {
        'cut_date': existing.get('cut_date') or '',
        'end_user': existing.get('end_user') or 'Internal',
        'customer_name_internal': existing.get('customer_name') if is_internal else '',
        'customer_name_external': existing.get('customer_name') if not is_internal else '',
        'internal_contact': existing.get('internal_contact') or '',
        'ro_number': existing.get('ro_number') or '',
        'vin': existing.get('vin') or '',
        'year': str(existing.get('year') or ''),
        'make': existing.get('make') or '',
        'model': existing.get('model') or '',
        'key_type': existing.get('key_type') or '',
        'key_fob_part_number': existing.get('key_fob_part_number') or '',
        'key_fob_cost': f"{float(existing['key_fob_cost']):.2f}" if existing.get('key_fob_cost') is not None else '',
        'key_blank_part_number': existing.get('key_blank_part_number') or '',
        'key_blank_cost': f"{float(existing['key_blank_cost']):.2f}" if existing.get('key_blank_cost') is not None else '',
        'programming_cost': f"{float(existing.get('programming_cost') or db.KEY_PROGRAMMING_COST_DEFAULT):.2f}",
        'offset_eligible': 'Y' if existing.get('offset_eligible') else 'N',
        'notes': existing.get('notes') or '',
    }
    return render_template(
        'mobile_key_form.html',
        **_mobile_key_form_context(form=form, key=existing),
    )


@app.route('/mobile-keys/<key_id>/delete', methods=['POST'])
def mobile_key_delete(key_id):
    try:
        db.delete_mobile_key(key_id)
    except Exception as e:
        logger.error(f"Delete mobile key failed: {e}")
    return redirect(url_for('mobile_keys_list'))


@app.route('/mobile-keys/<key_id>/toggle-status', methods=['POST'])
def mobile_key_toggle_status(key_id):
    status_done = request.form.get('status_done') == '1'
    try:
        db.set_mobile_key_status(key_id, status_done)
    except Exception as e:
        logger.error(f"Toggle status failed for {key_id}: {e}")
    return redirect(url_for('mobile_keys_list'))


@app.route('/mobile-keys/<key_id>/toggle-ordered', methods=['POST'])
def mobile_key_toggle_ordered(key_id):
    ordered = request.form.get('ordered') == '1'
    try:
        db.set_mobile_key_ordered(key_id, ordered)
    except Exception as e:
        logger.error(f"Toggle ordered failed for {key_id}: {e}")
    return redirect(url_for('mobile_keys_list'))


@app.route('/mobile-keys/<key_id>/key-code', methods=['POST'])
def mobile_key_set_key_code(key_id):
    # Driven by the Key Code modal: "Save" submits key_code=1 with the entered
    # text; "Uncheck" submits key_code=0 and the code is cleared.
    checked = request.form.get('key_code') == '1'
    code_value = (request.form.get('key_code_value') or '').strip() or None
    if not checked:
        code_value = None
    try:
        db.set_mobile_key_key_code(key_id, checked, code_value)
    except Exception as e:
        logger.error(f"Set key code failed for {key_id}: {e}")
    return redirect(url_for('mobile_keys_list'))


@app.route('/mobile-keys/<key_id>/notes', methods=['POST'])
def mobile_key_set_notes(key_id):
    # Driven by the Notes column modal on the list pages. Empty text clears it.
    notes = (request.form.get('notes') or '').strip() or None
    try:
        db.set_mobile_key_notes(key_id, notes)
    except Exception as e:
        logger.error(f"Set notes failed for {key_id}: {e}")
    # The same modal is used from the Inventory page — go back where we came from.
    if request.form.get('return_to') == 'inventory':
        return redirect(url_for('mobile_keys_inventory'))
    return redirect(url_for('mobile_keys_list'))


@app.route('/mobile-keys/api/reorder', methods=['POST'])
def mobile_key_reorder():
    payload = request.get_json(silent=True) or {}
    ids = payload.get('ids')
    if not isinstance(ids, list) or not all(isinstance(i, str) and i for i in ids):
        return jsonify({'ok': False, 'error': 'ids must be a list of strings'}), 400
    try:
        db.reorder_mobile_keys(ids)
    except Exception as e:
        logger.error(f"Reorder mobile keys failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500
    return jsonify({'ok': True})


@app.route('/mobile-keys/<key_id>/move-to-inventory', methods=['POST'])
def mobile_key_move_to_inventory(key_id):
    try:
        db.mark_mobile_key_in_inventory(key_id)
    except Exception as e:
        logger.error(f"Move-to-inventory failed for {key_id}: {e}")
    return redirect(url_for('mobile_keys_list'))


@app.route('/mobile-keys/<key_id>/restore-from-inventory', methods=['POST'])
def mobile_key_restore_from_inventory(key_id):
    try:
        db.clear_mobile_key_inventory(key_id)
    except Exception as e:
        logger.error(f"Restore-from-inventory failed for {key_id}: {e}")
    return redirect(url_for('mobile_keys_inventory'))


@app.route('/mobile-keys/inventory')
def mobile_keys_inventory():
    try:
        rows = db.list_mobile_keys_in_inventory()
    except Exception as e:
        logger.error(f"Failed to list mobile keys inventory: {e}")
        rows = []
    for r in rows:
        _compute_key_totals(r)
    return render_template('mobile_keys_inventory.html', keys=rows)


@app.route('/mobile-keys/contacts')
def mobile_key_contacts():
    try:
        contacts = db.list_key_code_contacts()
    except Exception as e:
        logger.error(f"Failed to list key code contacts: {e}")
        contacts = []
    return render_template('mobile_key_contacts.html', contacts=contacts)


def _clean_key_code_contact_payload(payload):
    """Pull store/name/email/notes out of a JSON payload, blanks -> None."""
    out = {}
    for field in ('store', 'name', 'email', 'notes'):
        if field in payload:
            out[field] = (payload.get(field) or '').strip() or None
    return out


@app.route('/mobile-keys/contacts/api/create', methods=['POST'])
def mobile_key_contacts_api_create():
    try:
        payload = request.get_json(silent=True) or {}
        data = _clean_key_code_contact_payload(payload)
        if not any(data.values()):
            return jsonify({'ok': False, 'error': 'empty contact'}), 400
        row = db.create_key_code_contact(data)
        return jsonify({'ok': True, 'row': row})
    except Exception as e:
        logger.error(f"key code contact create failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/mobile-keys/contacts/api/update/<contact_id>', methods=['POST'])
def mobile_key_contacts_api_update(contact_id):
    try:
        payload = request.get_json(silent=True) or {}
        data = _clean_key_code_contact_payload(payload)
        if not data:
            return jsonify({'ok': False, 'error': 'no fields to update'}), 400
        row = db.update_key_code_contact(contact_id, data)
        return jsonify({'ok': True, 'row': row})
    except Exception as e:
        logger.error(f"key code contact update failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/mobile-keys/contacts/api/delete/<contact_id>', methods=['POST'])
def mobile_key_contacts_api_delete(contact_id):
    try:
        db.delete_key_code_contact(contact_id)
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"key code contact delete failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"Starting Flask on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
