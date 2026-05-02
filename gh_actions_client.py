"""GitHub Actions client for delegating Ford recall checks.

Ford's Akamai blocks our DigitalOcean (and Fly.io, GCP) egress IPs but allows
GitHub Actions runners (Azure). When USE_GH_ACTIONS_FOR_RECALLS is set, the
Flask app dispatches the recall_check_on_demand workflow in this same repo,
polls until it completes, and downloads the resulting Excel as the job output.

Required env vars:
  GH_ACTIONS_TOKEN     PAT with `actions:write` + `actions:read` on the target repo
  GH_ACTIONS_REPO      e.g. "CGilbert23/FordRecallCheckScript"
  GH_ACTIONS_WORKFLOW  workflow filename (default "recall_check_on_demand.yml")
  GH_ACTIONS_REF       branch/ref to dispatch against (default "main")
"""
import io
import json
import logging
import os
import time
import uuid
import zipfile
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)

GH_API = "https://api.github.com"
DEFAULT_WORKFLOW = "recall_check_on_demand.yml"
DEFAULT_REF = "main"


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_required_env('GH_ACTIONS_TOKEN')}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _repo() -> str:
    return _required_env("GH_ACTIONS_REPO")


def _workflow() -> str:
    return os.environ.get("GH_ACTIONS_WORKFLOW") or DEFAULT_WORKFLOW


def _ref() -> str:
    return os.environ.get("GH_ACTIONS_REF") or DEFAULT_REF


def trigger_recall_check(vins: list[str], vin_units: Optional[dict] = None) -> str:
    """Dispatch the workflow. Returns the job_id we generated and passed in."""
    job_id = uuid.uuid4().hex[:12]
    payload = {
        "ref": _ref(),
        "inputs": {
            "job_id": job_id,
            "vins": "\n".join(vins),
            "vin_units_json": json.dumps(vin_units or {}),
        },
    }
    url = f"{GH_API}/repos/{_repo()}/actions/workflows/{_workflow()}/dispatches"
    r = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if r.status_code != 204:
        raise RuntimeError(f"workflow_dispatch failed: {r.status_code} {r.text[:500]}")
    logger.info(f"GH Actions dispatched: job_id={job_id} workflow={_workflow()} vins={len(vins)}")
    return job_id


def find_run_id(job_id: str, timeout: int = 90, poll_interval: int = 3) -> int:
    """workflow_dispatch returns no run_id, so we match by run-name set in the YAML."""
    target = f"Recall check {job_id}"
    url = f"{GH_API}/repos/{_repo()}/actions/workflows/{_workflow()}/runs"
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(url, headers=_headers(),
                         params={"event": "workflow_dispatch", "per_page": 30},
                         timeout=30)
        r.raise_for_status()
        for run in r.json().get("workflow_runs", []):
            if run.get("name") == target or run.get("display_title") == target:
                logger.info(f"GH Actions run_id={run['id']} found for job_id={job_id}")
                return run["id"]
        time.sleep(poll_interval)
    raise RuntimeError(f"Could not find run for job_id={job_id} within {timeout}s")


def wait_for_run(run_id: int, progress_callback: Optional[Callable] = None,
                 poll_interval: int = 10, timeout: int = 3600) -> dict:
    """Poll until the run completes (status=='completed'). Returns the run JSON."""
    url = f"{GH_API}/repos/{_repo()}/actions/runs/{run_id}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(url, headers=_headers(), timeout=30)
        r.raise_for_status()
        run = r.json()
        if progress_callback:
            progress_callback({"status": run.get("status"), "conclusion": run.get("conclusion")})
        if run.get("status") == "completed":
            return run
        time.sleep(poll_interval)
    raise RuntimeError(f"Run {run_id} did not complete within {timeout}s")


def download_artifact(run_id: int, job_id: str, dest_xlsx: str) -> dict:
    """Download the recall-result-<job_id> artifact zip, extract Excel to
    `dest_xlsx`, and return the parsed summary.json."""
    artifact_name = f"recall-result-{job_id}"
    url = f"{GH_API}/repos/{_repo()}/actions/runs/{run_id}/artifacts"
    r = requests.get(url, headers=_headers(), timeout=30)
    r.raise_for_status()
    artifact = next((a for a in r.json().get("artifacts", []) if a["name"] == artifact_name), None)
    if not artifact:
        raise RuntimeError(f"Artifact {artifact_name} not found for run {run_id}")

    dl = requests.get(artifact["archive_download_url"], headers=_headers(), timeout=120)
    dl.raise_for_status()

    summary: dict = {}
    with zipfile.ZipFile(io.BytesIO(dl.content)) as z:
        excel_name = next((n for n in z.namelist() if n.endswith(".xlsx")), None)
        summary_name = next((n for n in z.namelist() if n.endswith(".json")), None)
        if not excel_name:
            raise RuntimeError(f"No .xlsx in artifact {artifact_name}; got {z.namelist()}")
        with z.open(excel_name) as src, open(dest_xlsx, "wb") as out:
            out.write(src.read())
        if summary_name:
            with z.open(summary_name) as f:
                summary = json.loads(f.read().decode("utf-8"))
    return summary


def run_recall_check_via_actions(vins: list[str], output_file: str,
                                 progress_callback: Optional[Callable] = None,
                                 vin_units: Optional[dict] = None) -> dict:
    """Drop-in replacement for recall_checker.process_recalls() that delegates
    the Selenium scraping to a GitHub Actions run on Azure IPs. Returns the same
    summary shape: {processed, with_recalls, no_recalls, errors, max_recalls,
    output_file}."""
    if not vins:
        return {"error": "No VINs provided"}

    total = len(vins)

    def _emit(state: str, **extra):
        if progress_callback:
            progress_callback({"current": 0, "total": total, "status": state, **extra})

    _emit("dispatching")
    job_id = trigger_recall_check(vins, vin_units=vin_units)
    _emit("queued", job_id=job_id)

    run_id = find_run_id(job_id)
    _emit("running", job_id=job_id, run_id=run_id)

    def _on_run(info):
        if progress_callback:
            progress_callback({
                "current": 0, "total": total,
                "status": info.get("status") or "running",
                "job_id": job_id, "run_id": run_id,
            })

    run = wait_for_run(run_id, progress_callback=_on_run)
    if run.get("conclusion") != "success":
        raise RuntimeError(
            f"GH Actions run {run_id} failed: conclusion={run.get('conclusion')}"
        )

    summary = download_artifact(run_id, job_id, output_file)
    summary.setdefault("output_file", output_file)
    if progress_callback:
        progress_callback({
            "current": summary.get("processed", total),
            "total": total,
            "status": "complete",
            **summary,
        })
    return summary
