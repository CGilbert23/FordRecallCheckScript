import os
import logging
from supabase import create_client, Client

logger = logging.getLogger(__name__)

LOCATIONS = [
    'Doylestown', 'Boyertown', 'Newtown', 'Washington',
    'Exton', 'Langhorne', 'West Chester', 'Mechanicsburg', 'GroupWide',
]

CADENCES = ['daily', 'weekly', 'monthly', 'quarterly']

_client: Client | None = None


def get_client() -> Client:
    """Return a cached Supabase client. Raises if env vars are missing."""
    global _client
    if _client is not None:
        return _client

    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY')
    if not url or not key:
        raise RuntimeError(
            'SUPABASE_URL and SUPABASE_KEY must be set in the environment.'
        )

    _client = create_client(url, key)
    return _client


def ping() -> dict:
    """Verify the connection works by reading from schedules. Returns a small status dict."""
    client = get_client()
    res = client.table('schedules').select('id', count='exact').limit(1).execute()
    return {
        'ok': True,
        'schedules_count': res.count if res.count is not None else 0,
    }


def list_schedules():
    client = get_client()
    res = client.table('schedules').select('*').order('location').order('company_name').execute()
    return res.data or []


def get_schedule(schedule_id):
    client = get_client()
    res = client.table('schedules').select('*').eq('id', schedule_id).limit(1).execute()
    return res.data[0] if res.data else None


def create_schedule(data):
    client = get_client()
    res = client.table('schedules').insert(data).execute()
    return res.data[0] if res.data else None


def update_schedule(schedule_id, data):
    client = get_client()
    res = client.table('schedules').update(data).eq('id', schedule_id).execute()
    return res.data[0] if res.data else None


def delete_schedule(schedule_id):
    client = get_client()
    client.table('schedules').delete().eq('id', schedule_id).execute()


def list_runs(schedule_id, limit=10):
    client = get_client()
    res = (
        client.table('schedule_runs')
        .select('*')
        .eq('schedule_id', schedule_id)
        .order('started_at', desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def recent_runs_for_all(limit=50):
    """Recent runs across all schedules with the company/location joined in."""
    client = get_client()
    res = (
        client.table('schedule_runs')
        .select('*, schedules(company_name, location, cadence)')
        .order('started_at', desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def create_run(schedule_id, vin_count, triggered_by='scheduled'):
    client = get_client()
    res = client.table('schedule_runs').insert({
        'schedule_id': schedule_id,
        'vin_count': vin_count,
        'triggered_by': triggered_by,
    }).execute()
    return res.data[0] if res.data else None


def finish_run(run_id, recalls_found=None, email_sent=False, error=None):
    from datetime import datetime, timezone
    client = get_client()
    client.table('schedule_runs').update({
        'finished_at': datetime.now(timezone.utc).isoformat(),
        'recalls_found': recalls_found,
        'email_sent': email_sent,
        'error': error,
    }).eq('id', run_id).execute()
