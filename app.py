import os
import sys
import uuid
import queue
import threading
import logging
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, request, render_template, jsonify, send_file, redirect, url_for
from recall_checker import process_recalls
import resend
import io
import openpyxl
import db
import scheduler

# Log everything to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

resend.api_key = os.environ.get('RESEND_API_KEY', '')
RESEND_FROM_EMAIL = os.environ.get('RESEND_FROM_EMAIL', 'fordrecalls@voxapp.co')

# In-memory job store and queue
jobs = {}
job_queue = queue.Queue()

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

    try:
        logger.info(f"Job {job_id}: starting with {len(vins)} VINs")
        jobs[job_id]['status'] = 'running'
        result = process_recalls(vins, output_file, progress_callback=on_progress, vin_units=vin_units)
        jobs[job_id]['status'] = 'complete'
        jobs[job_id]['result'] = result
        jobs[job_id]['output_file'] = output_file
        recalls_found = result.get('with_recalls', 0)
        logger.info(f"Job {job_id}: complete - {recalls_found} recalls found")

        is_scheduled = meta.get('schedule_run_id') is not None
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


@app.route('/recall/one-time')
def one_time_form():
    active = sum(1 for j in jobs.values() if j['status'] in ('running', 'starting', 'queued'))
    return render_template('index.html', active_jobs=active)


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

    email = request.form.get('email', '').strip()
    name = request.form.get('name', '').strip()

    job_id = uuid.uuid4().hex[:12]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = ''.join(c for c in name if c.isalnum() or c in ' _-').strip().replace(' ', '_')
    if safe_name:
        filename = f'{safe_name}_Ford_Recalls_{timestamp}.xlsx'
    else:
        filename = f'Ford_Recalls_{timestamp}.xlsx'
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
    sorted_jobs = sorted(jobs.items(), key=lambda x: x[1].get('started', ''), reverse=True)
    return render_template('dashboard.html', jobs=sorted_jobs)


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
    fleet_manager_phone = req.form.get('fleet_manager_phone', '').strip()
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
        'fleet_manager_email': form['fleet_manager_email'] or None,
        'fleet_manager_phone': form['fleet_manager_phone'] or None,
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
        if error:
            return render_template(
                'account_form.html', account=None, form=form, error=error,
                markets=db.MARKETS, reps=db.ACCOUNT_REPS, service_types=db.SERVICE_TYPES,
                from_lead_id=from_lead_id,
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
        'fleet_manager_email': existing.get('fleet_manager_email') or '',
        'fleet_manager_phone': existing.get('fleet_manager_phone') or '',
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
# CRM: Leads
# ---------------------------------------------------------------------------

def _read_lead_form(req):
    company_name = req.form.get('company_name', '').strip()
    market = req.form.get('market', '').strip()
    account_rep = req.form.get('account_rep', '').strip()
    phone = req.form.get('phone', '').strip()
    lead_source = req.form.get('lead_source', '').strip()
    lead_source_other = req.form.get('lead_source_other', '').strip()
    notes = req.form.get('notes', '').strip()

    form = {
        'company_name': company_name,
        'market': market,
        'account_rep': account_rep,
        'phone': phone,
        'lead_source': lead_source,
        'lead_source_other': lead_source_other,
        'notes': notes,
    }
    if not company_name:
        return form, 'Company name is required.'
    if market not in db.MARKETS:
        return form, 'Please pick a valid market.'
    if account_rep not in db.ACCOUNT_REPS:
        return form, 'Please pick a valid account representative.'
    if lead_source and lead_source not in db.LEAD_SOURCES:
        return form, 'Please pick a valid lead source.'
    if lead_source == 'Other' and not lead_source_other:
        return form, 'Please describe the lead source when "Other" is selected.'
    return form, None


def _lead_payload(form):
    return {
        'company_name': form['company_name'],
        'market': form['market'],
        'account_rep': form['account_rep'],
        'phone': form['phone'] or None,
        'lead_source': form['lead_source'] or None,
        # Free-text only meaningful when source is Other; clear it otherwise
        # so the column doesn't carry stale data after the dropdown changes.
        'lead_source_other': form['lead_source_other'] if form['lead_source'] == 'Other' else None,
        'notes': form['notes'] or None,
    }


@app.route('/leads')
def leads_list():
    try:
        leads = db.list_leads(include_converted=False)
    except Exception as e:
        logger.error(f"Failed to load leads: {e}")
        leads = []
    return render_template(
        'leads.html',
        leads=leads,
        markets=db.MARKETS,
        reps=db.ACCOUNT_REPS,
    )


@app.route('/leads/new', methods=['GET', 'POST'])
def lead_new():
    if request.method == 'POST':
        form, error = _read_lead_form(request)
        if error:
            return render_template(
                'lead_form.html', lead=None, form=form, error=error,
                markets=db.MARKETS, reps=db.ACCOUNT_REPS, lead_sources=db.LEAD_SOURCES,
            )
        try:
            db.create_lead(_lead_payload(form))
        except Exception as e:
            logger.error(f"Create lead failed: {e}")
            return render_template(
                'lead_form.html', lead=None, form=form, error=str(e),
                markets=db.MARKETS, reps=db.ACCOUNT_REPS, lead_sources=db.LEAD_SOURCES,
            )
        return redirect(url_for('leads_list'))

    return render_template(
        'lead_form.html', lead=None, form={},
        markets=db.MARKETS, reps=db.ACCOUNT_REPS, lead_sources=db.LEAD_SOURCES,
    )


@app.route('/leads/<lead_id>/edit', methods=['GET', 'POST'])
def lead_edit(lead_id):
    try:
        existing = db.get_lead(lead_id)
    except Exception as e:
        logger.error(f"Failed to load lead {lead_id}: {e}")
        existing = None
    if not existing:
        return 'Lead not found', 404

    if request.method == 'POST':
        form, error = _read_lead_form(request)
        if error:
            return render_template(
                'lead_form.html', lead=existing, form=form, error=error,
                markets=db.MARKETS, reps=db.ACCOUNT_REPS, lead_sources=db.LEAD_SOURCES,
            )
        try:
            db.update_lead(lead_id, _lead_payload(form))
        except Exception as e:
            logger.error(f"Update lead failed: {e}")
            return render_template(
                'lead_form.html', lead=existing, form=form, error=str(e),
                markets=db.MARKETS, reps=db.ACCOUNT_REPS, lead_sources=db.LEAD_SOURCES,
            )
        return redirect(url_for('leads_list'))

    form = {
        'company_name': existing.get('company_name') or '',
        'market': existing.get('market') or '',
        'account_rep': existing.get('account_rep') or '',
        'phone': existing.get('phone') or '',
        'lead_source': existing.get('lead_source') or '',
        'lead_source_other': existing.get('lead_source_other') or '',
        'notes': existing.get('notes') or '',
    }
    return render_template(
        'lead_form.html', lead=existing, form=form,
        markets=db.MARKETS, reps=db.ACCOUNT_REPS, lead_sources=db.LEAD_SOURCES,
    )


@app.route('/leads/<lead_id>/delete', methods=['POST'])
def lead_delete(lead_id):
    try:
        db.delete_lead(lead_id)
    except Exception as e:
        logger.error(f"Delete lead failed: {e}")
    return redirect(url_for('leads_list'))


@app.route('/leads/<lead_id>/convert')
def lead_convert(lead_id):
    """Render the New Account form pre-filled with the lead's data.

    The account form posts to /accounts/new with a hidden from_lead_id; that
    handler calls convert_lead_to_account so the lead is only marked converted
    once the account row is successfully created.
    """
    try:
        lead = db.get_lead(lead_id)
    except Exception as e:
        logger.error(f"Failed to load lead {lead_id}: {e}")
        lead = None
    if not lead:
        return 'Lead not found', 404

    form = {
        'company_name': lead.get('company_name') or '',
        'market': lead.get('market') or '',
        'account_rep': lead.get('account_rep') or '',
        'fleet_manager_phone': lead.get('phone') or '',
        'notes': lead.get('notes') or '',
    }
    return render_template(
        'account_form.html', account=None, form=form,
        markets=db.MARKETS, reps=db.ACCOUNT_REPS, service_types=db.SERVICE_TYPES,
        from_lead_id=lead_id,
    )


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"Starting Flask on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
