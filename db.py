import os
import logging
from supabase import create_client, Client

logger = logging.getLogger(__name__)

MARKETS = [
    'Boyertown', 'Doylestown', 'Exton', 'Langhorne', 'Newtown',
    'Washington', 'West Chester', 'Mechanicsburg', 'Company-Wide',
]
LOCATIONS = MARKETS  # back-compat alias for existing callers

ACCOUNT_REPS = [
    'Steven Nawalany', 'Chris Gilbert', 'Erica Stewart',
    'Shelbi Good', 'Cliff Allen', 'Scott Voyzey', 'Frank Smith',
]

# Default recipient email per rep. Used to prefill the recipients textarea on
# new schedules. mobileservice@fredbeans.com is auto-CC'd elsewhere, so it's
# intentionally not duplicated here.
ACCOUNT_REP_EMAILS = {
    'Steven Nawalany': 'SNawalany@fredbeans.com',
    'Chris Gilbert': 'chris.gilbert@fredbeans.com',
    'Erica Stewart': 'estewart@fredbeans.com',
    'Shelbi Good': 'sgood@fredbeans.com',
    'Cliff Allen': 'callen@fredbeans.com',
    'Scott Voyzey': 'svoyzey@fredbeans.com',
    'Frank Smith': 'fsmith@fredbeans.com',
}

SERVICE_TYPES = ['Full Service', 'Recall Only']

LEAD_SOURCES = ['Sales', 'Service', 'Visual', 'Other']

LEAD_TYPES = ['cold', 'warm']
INTEREST_LEVELS = ['R', 'Y', 'G']
INTEREST_LEVEL_DEFAULT = 'Y'

CADENCES = ['daily', 'weekly', 'monthly', 'quarterly']

ACCOUNT_CHECK_IN_DAYS = 25

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


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def list_accounts():
    client = get_client()
    res = client.table('accounts').select('*').order('account_rep').order('company_name').execute()
    return res.data or []


def list_accounts_grouped_by_rep():
    """Return an ordered dict of {rep: [accounts]} with all reps present (empty buckets included)."""
    grouped = {rep: [] for rep in ACCOUNT_REPS}
    for acct in list_accounts():
        rep = acct.get('account_rep')
        grouped.setdefault(rep, []).append(acct)
    return grouped


def get_account(account_id):
    client = get_client()
    res = client.table('accounts').select('*').eq('id', account_id).limit(1).execute()
    return res.data[0] if res.data else None


def create_account(data):
    client = get_client()
    res = client.table('accounts').insert(data).execute()
    return res.data[0] if res.data else None


def update_account(account_id, data):
    client = get_client()
    res = client.table('accounts').update(data).eq('id', account_id).execute()
    return res.data[0] if res.data else None


def mark_account_checked_in(account_id):
    from datetime import datetime, timezone
    client = get_client()
    res = client.table('accounts').update({
        'last_checked_in_at': datetime.now(timezone.utc).isoformat(),
    }).eq('id', account_id).execute()
    return res.data[0] if res.data else None


def delete_account(account_id):
    client = get_client()
    client.table('accounts').delete().eq('id', account_id).execute()


def list_schedules_for_account(account_id):
    client = get_client()
    res = client.table('schedules').select('*').eq('account_id', account_id).execute()
    return res.data or []


# ---------------------------------------------------------------------------
# Account leads
# ---------------------------------------------------------------------------

def list_leads(include_converted=False, lead_type=None):
    client = get_client()
    query = client.table('account_leads').select('*').order('account_rep').order('company_name')
    if not include_converted:
        query = query.is_('converted_at', 'null')
    if lead_type:
        query = query.eq('lead_type', lead_type)
    res = query.execute()
    return res.data or []


def promote_lead_to_warm(lead_id):
    client = get_client()
    res = client.table('account_leads').update({
        'lead_type': 'warm',
    }).eq('id', lead_id).execute()
    return res.data[0] if res.data else None


def get_lead(lead_id):
    client = get_client()
    res = client.table('account_leads').select('*').eq('id', lead_id).limit(1).execute()
    return res.data[0] if res.data else None


def create_lead(data):
    client = get_client()
    res = client.table('account_leads').insert(data).execute()
    return res.data[0] if res.data else None


def update_lead(lead_id, data):
    client = get_client()
    res = client.table('account_leads').update(data).eq('id', lead_id).execute()
    return res.data[0] if res.data else None


def delete_lead(lead_id):
    client = get_client()
    client.table('account_leads').delete().eq('id', lead_id).execute()


def convert_lead_to_account(lead_id, account_data):
    """Create an account from lead data, then mark the lead converted.

    The account insert happens first; only on success do we update the lead. If
    the account insert fails, the lead is left untouched so the caller can
    surface a validation error and let the user retry.
    """
    from datetime import datetime, timezone
    account = create_account(account_data)
    if not account:
        return None
    client = get_client()
    client.table('account_leads').update({
        'converted_at': datetime.now(timezone.utc).isoformat(),
        'converted_account_id': account['id'],
    }).eq('id', lead_id).execute()
    return account
