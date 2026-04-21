"""Background scheduler for recurring recall checks.

Registers one cron trigger per active schedule, all firing at 6:00 AM America/New_York.
Fire callback enqueues a job onto the app's existing job_queue so scheduled runs share
the same serialization/worker as ad-hoc submissions.
"""
import logging
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import db

logger = logging.getLogger(__name__)

TZ = ZoneInfo('America/New_York')

_scheduler: BackgroundScheduler | None = None
_fire_callback = None


def _cron_for(cadence: str) -> CronTrigger:
    """Return a CronTrigger for the given cadence, all at 6am ET."""
    if cadence == 'daily':
        return CronTrigger(hour=6, minute=0, timezone=TZ)
    if cadence == 'weekly':
        # Monday 6am
        return CronTrigger(day_of_week='mon', hour=6, minute=0, timezone=TZ)
    if cadence == 'monthly':
        # 1st of the month, 6am
        return CronTrigger(day=1, hour=6, minute=0, timezone=TZ)
    if cadence == 'quarterly':
        # 1st of Jan/Apr/Jul/Oct, 6am
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
    trigger = _cron_for(cadence)
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


def _fire(schedule_id: str):
    """Called by APScheduler when a cron trigger fires."""
    if _fire_callback is None:
        logger.error('Scheduler fired but no callback is set')
        return
    try:
        _fire_callback(schedule_id, triggered_by='scheduled')
    except Exception as e:
        logger.error(f'Scheduler fire failed for {schedule_id}: {e}')
