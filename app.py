import os
import sys
import uuid
import threading
import logging
from datetime import datetime
from flask import Flask, request, render_template, jsonify, send_file, redirect, url_for
from recall_checker import process_recalls
import resend

# Log everything to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

resend.api_key = os.environ.get('RESEND_API_KEY', '')
RESEND_FROM_EMAIL = os.environ.get('RESEND_FROM_EMAIL', 'fordrecalls@voxapp.co')

# In-memory job store
jobs = {}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, 'outputs')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def send_results_email(email, output_file, result):
    """Send the Excel results file to the user via Resend."""
    try:
        filename = os.path.basename(output_file)
        with open(output_file, 'rb') as f:
            file_content = list(f.read())

        with_recalls = result.get('with_recalls', 0)
        processed = result.get('processed', 0)

        resend.Emails.send({
            "from": RESEND_FROM_EMAIL,
            "to": [email],
            "subject": f"Ford Recall Results - {with_recalls} recall(s) found",
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
        logger.info(f"Results email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {str(e)}")
        return False


def run_job(job_id, vins, output_file):
    def on_progress(data):
        jobs[job_id]['progress'] = data

    try:
        logger.info(f"Job {job_id}: starting with {len(vins)} VINs")
        jobs[job_id]['status'] = 'running'
        result = process_recalls(vins, output_file, progress_callback=on_progress)
        jobs[job_id]['status'] = 'complete'
        jobs[job_id]['result'] = result
        jobs[job_id]['output_file'] = output_file
        logger.info(f"Job {job_id}: complete - {result.get('with_recalls', 0)} recalls found")

        # Send email if one was provided
        email = jobs[job_id].get('email')
        if email:
            sent = send_results_email(email, output_file, result)
            jobs[job_id]['email_sent'] = sent
    except Exception as e:
        logger.error(f"Job {job_id}: FAILED - {str(e)}")
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['error'] = str(e)


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


@app.route('/')
def index():
    running = any(j['status'] == 'running' for j in jobs.values())
    return render_template('index.html', running=running)


@app.route('/submit', methods=['POST'])
def submit():
    logger.info("Submit received")

    if any(j['status'] == 'running' for j in jobs.values()):
        return render_template('index.html', running=True, error='A job is already running. Please wait for it to finish.')

    text = request.form.get('vins', '')
    vins = [line.strip() for line in text.splitlines() if line.strip()]

    vins = [v.upper() for v in vins if len(v) == 17 and v.isalnum()]

    logger.info(f"Parsed {len(vins)} valid VINs")

    if not vins:
        return render_template('index.html', running=False, error='No valid VINs found. Each VIN must be exactly 17 alphanumeric characters.')

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

    jobs[job_id] = {
        'status': 'starting',
        'progress': {'current': 0, 'total': len(vins), 'status': 'starting'},
        'output_file': output_file,
        'started': datetime.now().isoformat(),
        'vin_count': len(vins),
        'email': email or None,
        'name': name or None,
    }

    logger.info(f"Created job {job_id}")

    t = threading.Thread(target=run_job, args=(job_id, vins, output_file))
    t.start()

    logger.info(f"Thread started for job {job_id}")

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


@app.route('/download/<job_id>')
def download(job_id):
    if job_id not in jobs:
        return 'Job not found', 404
    job = jobs[job_id]
    if job['status'] != 'complete' or not os.path.exists(job.get('output_file', '')):
        return 'File not ready', 400
    return send_file(job['output_file'], as_attachment=True, download_name=os.path.basename(job['output_file']))


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"Starting Flask on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
