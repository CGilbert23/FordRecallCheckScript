"""Background scheduler for recurring recall checks.

Registers one cron trigger per active schedule, all firing at 6:00 AM America/New_York.
Fire callback enqueues a job onto the app's existing job_queue so scheduled runs share
the same serialization/worker as ad-hoc submissions.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import db

logger = logging.getLogger(__name__)

TZ = ZoneInfo('America/New_York')

_scheduler: BackgroundScheduler | None = None
_fire_callback = None


_INTERVAL_DAYS = {'monthly': 30, 'quarterly': 90}


def _parse_anchor(anchor_at):
    """Coerce a Supabase `anchor_at` (str or datetime, possibly null) to a
    tz-aware datetime, or None if not set."""
    if not anchor_at:
        return None
    if isinstance(anchor_at, datetime):
        dt = anchor_at
    else:
        # Supabase returns ISO 8601, e.g. "2026-06-10T10:00:00+00:00".
        dt = datetime.fromisoformat(anchor_at.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt


def _trigger_for(schedule: dict):
    """Return an APScheduler trigger for the given schedule row.

    - daily: cron at 6am ET (no anchor needed).
    - monthly/quarterly with an anchor_at: IntervalTrigger every 30/90 days
      starting at anchor_at. APScheduler advances to the next future tick
      automatically if anchor_at is in the past.
    - monthly/quarterly without an anchor_at (legacy rows): the old
      cron-on-the-1st behavior, preserved so pre-migration schedules don't
      shift unexpectedly.
    """
    cadence = schedule['cadence']
    if cadence == 'daily':
        return CronTrigger(hour=6, minute=0, timezone=TZ)
    if cadence in _INTERVAL_DAYS:
        anchor = _parse_anchor(schedule.get('anchor_at'))
        if anchor is not None:
            return IntervalTrigger(days=_INTERVAL_DAYS[cadence], start_date=anchor, timezone=TZ)
        if cadence == 'monthly':
            return CronTrigger(day=1, hour=6, minute=0, timezone=TZ)
        return CronTrigger(month='1,4,7,10', day=1, hour=6, minute=0, timezone=TZ)
    raise ValueError(f'Unknown cadence: {cadence}')


def start(fire_callback):
    """Initialize the scheduler and register triggers for all active schedules.

    `fire_callback(schedule_id)` will be called when a scheduled run should execute.
    """
    global _scheduler, _fire_callback
    if _scheduler is not None:
        logger.warning('Scheduler already started; skipping')
        return

    _fire_callback = fire_callback
    _scheduler = BackgroundScheduler(timezone=TZ)
    _scheduler.start()
    logger.info('APScheduler started (America/New_York)')

    try:
        schedules = db.list_schedules()
    except Exception as e:
        logger.error(f'Could not load schedules on scheduler start: {e}')
        return

    for s in schedules:
        if s.get('active'):
            register(s)


def register(schedule: dict):
    """Add or replace the trigger for a schedule."""
    if _scheduler is None:
        return
    schedule_id = schedule['id']
    cadence = schedule['cadence']
    trigger = _trigger_for(schedule)
    _scheduler.add_job(
        _fire,
        trigger=trigger,
        id=str(schedule_id),
        args=[schedule_id],
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info(f'Registered schedule {schedule_id} ({cadence})')


def unregister(schedule_id: str):
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(str(schedule_id))
        logger.info(f'Unregistered schedule {schedule_id}')
    except Exception:
        pass  # Job wasn't registered — fine.


def next_run_time(schedule_id: str):
    """Return the next firing datetime (tz-aware, ET) for an active schedule,
    or None if it isn't registered (paused/inactive or scheduler not started)."""
    if _scheduler is None:
        return None
    try:
        job = _scheduler.get_job(str(schedule_id))
    except Exception:
        return None
    return job.next_run_time if job else None


def _fire(schedule_id: str):
    """Called by APScheduler when a cron trigger fires."""
    if _fire_callback is None:
        logger.error('Scheduler fired but no callback is set')
        return
    try:
        _fire_callback(schedule_id, triggered_by='scheduled')
    except Exception as e:
        logger.error(f'Scheduler fire failed for {schedule_id}: {e}')
