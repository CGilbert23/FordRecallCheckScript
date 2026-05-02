"""Entry point for the recall_check_on_demand GitHub Actions workflow.

Reads VINs / job_id / vin_units from env vars (set by workflow_dispatch inputs),
calls the existing process_recalls() to do the actual Selenium scraping and
Excel building, then writes a summary.json that the Flask client downloads
alongside the Excel as a workflow artifact.

Inside the workflow USE_GH_ACTIONS_FOR_RECALLS is left unset, so process_recalls
falls through to the direct Selenium path (no recursive dispatch).
"""
import json
import os
from pathlib import Path

from recall_checker import process_recalls

JOB_ID = os.environ["JOB_ID"].strip()
VINS = [v.strip().upper() for v in os.environ["JOB_VINS"].splitlines() if v.strip()]
_units_raw = json.loads(os.environ.get("JOB_VIN_UNITS") or "{}")
VIN_UNITS = _units_raw or None  # process_recalls treats None as "no Unit # column"

OUT_DIR = Path("recall_output")
OUT_DIR.mkdir(exist_ok=True)
EXCEL_PATH = OUT_DIR / f"recall_{JOB_ID}.xlsx"
SUMMARY_PATH = OUT_DIR / f"summary_{JOB_ID}.json"

print(f"[{JOB_ID}] Starting recall check for {len(VINS)} VIN(s)", flush=True)


def on_progress(p):
    print(f"[{JOB_ID}] progress {p}", flush=True)


result = process_recalls(VINS, str(EXCEL_PATH),
                         progress_callback=on_progress, vin_units=VIN_UNITS)
result["job_id"] = JOB_ID
SUMMARY_PATH.write_text(json.dumps(result, indent=2, default=str))
print(f"[{JOB_ID}] Done. {result}", flush=True)
