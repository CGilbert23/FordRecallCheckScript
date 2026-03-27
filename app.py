import os
import uuid
import threading
from datetime import datetime
from flask import Flask, request, render_template, jsonify, send_file, redirect, url_for
from recall_checker import process_recalls

app = Flask(__name__)

# In-memory job store
jobs = {}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, 'outputs')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_job(job_id, vins, output_file):
    def on_progress(data):
        jobs[job_id]['progress'] = data

    try:
        jobs[job_id]['status'] = 'running'
        result = process_recalls(vins, output_file, progress_callback=on_progress)
        jobs[job_id]['status'] = 'complete'
        jobs[job_id]['result'] = result
        jobs[job_id]['output_file'] = output_file
    except Exception as e:
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['error'] = str(e)


@app.route('/')
def index():
    # Check if a job is currently running
    running = any(j['status'] == 'running' for j in jobs.values())
    return render_template('index.html', running=running)


@app.route('/submit', methods=['POST'])
def submit():
    # Block if a job is already running
    if any(j['status'] == 'running' for j in jobs.values()):
        return render_template('index.html', running=True, error='A job is already running. Please wait for it to finish.')

    vins = []

    # Check for file upload first
    uploaded = request.files.get('vinfile')
    if uploaded and uploaded.filename:
        content = uploaded.read().decode('utf-8', errors='ignore')
        vins = [line.strip() for line in content.splitlines() if line.strip()]

    # Fall back to textarea
    if not vins:
        text = request.form.get('vins', '')
        vins = [line.strip() for line in text.splitlines() if line.strip()]

    # Basic validation
    vins = [v.upper() for v in vins if len(v) == 17 and v.isalnum()]

    if not vins:
        return render_template('index.html', running=False, error='No valid VINs found. Each VIN must be exactly 17 alphanumeric characters.')

    job_id = uuid.uuid4().hex[:12]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f'FORD_RECALLS_{job_id}_{timestamp}.xlsx')

    jobs[job_id] = {
        'status': 'starting',
        'progress': {'current': 0, 'total': len(vins), 'status': 'starting'},
        'output_file': output_file,
        'started': datetime.now().isoformat(),
        'vin_count': len(vins),
    }

    t = threading.Thread(target=run_job, args=(job_id, vins, output_file), daemon=True)
    t.start()

    return redirect(url_for('job_page', job_id=job_id))


@app.route('/job/<job_id>')
def job_page(job_id):
    if job_id not in jobs:
        return 'Job not found', 404
    return render_template('status.html', job_id=job_id, job=jobs[job_id])


@app.route('/status/<job_id>')
def status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
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
    app.run(host='0.0.0.0', port=5000, debug=False)
