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

LEAD_TYPES = ['cold', 'warm']
INTEREST_LEVELS = ['R', 'Y', 'G']
INTEREST_LEVEL_DEFAULT = 'Y'

LEAD_ATTEMPT_OUTCOMES = ['made_contact', 'left_voicemail']
LEAD_CLOSE_REASONS = ['not_interested']

CADENCES = ['daily', 'monthly', 'quarterly']

# Mobile Keys section. Internal cuts go to a Fred Beans-affiliated store from
# the dropdown; customer cuts are free text. The 'Bid Lot' entry covers our
# own auction lot inventory — internally tracked but not a brand.
KEY_END_USERS = ['Internal', 'Customer']
KEY_INTERNAL_CUSTOMERS = [
    'FB Chevrolet', 'FB CDJR', 'FB Hyundai', 'FB Lincoln', 'FB Ford', 'FB Subaru', 'FB Toyota', 'Bid Lot',
]
KEY_MAKES = [
    'Acura', 'Buick', 'Cadillac', 'Chevrolet', 'Chrysler', 'Dodge', 'Ford',
    'Genesis', 'GMC', 'Honda', 'Hyundai', 'Infiniti', 'Jeep', 'Kia', 'Lexus',
    'Lincoln', 'Mazda', 'Nissan', 'Ram', 'Subaru', 'Toyota',
]
KEY_TYPES = ['Fob', 'Turnkey', 'Flip Key']
KEY_PROGRAMMING_COST_DEFAULT = 60.00
KEY_PROGRAMMING_COST_INTERNAL = 60.00
KEY_PROGRAMMING_COST_CUSTOMER = 100.00
# Parts markup applied to the billed Total, by who's billed.
KEY_MARKUP_INTERNAL = 0.10
KEY_MARKUP_CUSTOMER = 0.35

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
# One-time runs (ad-hoc /submit jobs — persisted so the run log survives
# container restarts; the in-memory `jobs` dict in app.py is still used for
# live progress polling)
# ---------------------------------------------------------------------------

def create_one_time_run(job_id, vins, status='queued', customer_name=None,
                        output_file=None, email=None):
    client = get_client()
    res = client.table('one_time_runs').insert({
        'job_id': job_id,
        'status': status,
        'vin_count': len(vins),
        'vins': list(vins),
        'customer_name': customer_name,
        'output_file': output_file,
        'email': email,
    }).execute()
    return res.data[0] if res.data else None


def update_one_time_run(job_id, **fields):
    """Patch a one-time run row. Pass any subset of: status, recalls_found,
    finished_at, output_file, email_sent, error. Caller controls finished_at
    (we don't auto-stamp it — some transitions like queued->running shouldn't)."""
    if not fields:
        return None
    client = get_client()
    res = client.table('one_time_runs').update(fields).eq('job_id', job_id).execute()
    return res.data[0] if res.data else None


def list_one_time_runs(limit=100):
    client = get_client()
    res = (
        client.table('one_time_runs')
        .select('*')
        .order('started_at', desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


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
        # `include_converted=False` also hides leads we've soft-closed via
        # the Not Interested action — same idea: keep the active list clean.
        query = query.is_('converted_at', 'null').is_('closed_at', 'null')
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


def record_lead_attempt(lead_id, attempt_at, outcome, note=None):
    """Stamp the lead row with the latest contact attempt date + outcome.

    `note` is required by the UI for made_contact outcomes and ignored
    (stored as null) for voicemail outcomes. Always written so the column
    clears when the latest attempt has no note.
    """
    client = get_client()
    res = client.table('account_leads').update({
        'last_attempt_at': attempt_at,
        'last_attempt_outcome': outcome,
        'last_attempt_note': note,
    }).eq('id', lead_id).execute()
    return res.data[0] if res.data else None


def close_lead(lead_id, reason='not_interested'):
    """Soft-close a lead so it disappears from the active cold list."""
    from datetime import datetime, timezone
    client = get_client()
    res = client.table('account_leads').update({
        'closed_at': datetime.now(timezone.utc).isoformat(),
        'closed_reason': reason,
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


def _digits_only(s):
    return ''.join(c for c in (s or '') if c.isdigit())


def find_duplicate_matches(company_name=None, emails=None, phones=None):
    """Search accounts + active leads for soft-duplicate matches.

    Match rules:
      - company_name: case-insensitive exact match (whitespace stripped)
      - emails: case-insensitive exact match (sentinel '--' ignored)
      - phones: digits-only exact match

    Returns a list of dicts: {table, id, company_name, market, field, value}.
    Converted leads are skipped because the resulting account already matches.
    """
    name_lc = (company_name or '').strip().lower()
    email_set = {e.strip().lower() for e in (emails or []) if e and e.strip() and e.strip() != '--'}
    phone_set = {_digits_only(p) for p in (phones or []) if _digits_only(p)}

    if not name_lc and not email_set and not phone_set:
        return []

    matches = []
    seen_keys = set()  # de-dupe (table, id, field) so one row only appears once per field

    def add(table, row, field, value):
        key = (table, row.get('id'), field)
        if key in seen_keys:
            return
        seen_keys.add(key)
        matches.append({
            'table': table,
            'id': row.get('id'),
            'company_name': row.get('company_name'),
            'market': row.get('market') or row.get('location'),
            'field': field,
            'value': value,
        })

    for a in list_accounts():
        if name_lc and (a.get('company_name') or '').strip().lower() == name_lc:
            add('accounts', a, 'company_name', a.get('company_name'))
        for fld in ('fleet_manager_email', 'fleet_manager_2_email'):
            v = (a.get(fld) or '').strip().lower()
            if v and v != '--' and v in email_set:
                add('accounts', a, 'email', a.get(fld))
        for fld in ('fleet_manager_phone', 'fleet_manager_2_phone'):
            v = _digits_only(a.get(fld))
            if v and v in phone_set:
                add('accounts', a, 'phone', a.get(fld))

    leads = [l for l in list_leads(include_converted=True) if not l.get('converted_at')]
    for l in leads:
        if name_lc and (l.get('company_name') or '').strip().lower() == name_lc:
            add('leads', l, 'company_name', l.get('company_name'))
        v = (l.get('fleet_manager_email') or '').strip().lower()
        if v and v in email_set:
            add('leads', l, 'email', l.get('fleet_manager_email'))
        v = _digits_only(l.get('phone'))
        if v and v in phone_set:
            add('leads', l, 'phone', l.get('phone'))

    return matches


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


# ---------------------------------------------------------------------------
# Mobile keys
# ---------------------------------------------------------------------------

def list_mobile_keys():
    client = get_client()
    res = (
        client.table('mobile_keys')
        .select('*')
        .is_('moved_to_inventory_at', 'null')
        .order('sort_order', desc=False)
        .execute()
    )
    return res.data or []


def get_mobile_key(key_id):
    client = get_client()
    res = client.table('mobile_keys').select('*').eq('id', key_id).limit(1).execute()
    return res.data[0] if res.data else None


def create_mobile_key(data):
    client = get_client()
    # New rows go to the top of the manual order: min(sort_order) - 1.
    top = (
        client.table('mobile_keys')
        .select('sort_order')
        .order('sort_order', desc=False)
        .limit(1)
        .execute()
    )
    current_min = top.data[0]['sort_order'] if top.data else 0
    payload = dict(data)
    payload['sort_order'] = current_min - 1
    res = client.table('mobile_keys').insert(payload).execute()
    return res.data[0] if res.data else None


def reorder_mobile_keys(ids):
    """Persist a new manual order. `ids` is the list of key UUIDs in the
    visual order the user dropped them into; each gets sort_order = index."""
    client = get_client()
    for index, key_id in enumerate(ids):
        client.table('mobile_keys').update({
            'sort_order': index,
        }).eq('id', key_id).execute()


def update_mobile_key(key_id, data):
    client = get_client()
    res = client.table('mobile_keys').update(data).eq('id', key_id).execute()
    return res.data[0] if res.data else None


def bulk_update_mobile_keys(updates):
    """Apply a list of {'id': ..., **fields} partial updates.

    Returns (applied_count, errors) where errors is [(id, message), ...]. A row
    that fails doesn't stop the rest — the invoice import reports per-row.
    Loop of single-row updates, same shape as reorder_mobile_keys: Supabase has
    no per-row bulk update and these batches are a handful of rows.
    """
    client = get_client()
    applied = 0
    errors = []
    for update in updates:
        data = {k: v for k, v in update.items() if k != 'id'}
        if not data:
            continue
        try:
            res = client.table('mobile_keys').update(data).eq('id', update['id']).execute()
            # An update against an id that no longer exists succeeds but changes
            # nothing, so count what actually came back rather than attempts.
            if res.data:
                applied += 1
            else:
                errors.append((update['id'], 'key no longer exists'))
        except Exception as e:
            errors.append((update['id'], str(e)))
    return applied, errors


def delete_mobile_key(key_id):
    client = get_client()
    client.table('mobile_keys').delete().eq('id', key_id).execute()


def mark_mobile_key_in_inventory(key_id):
    """Stamp moved_to_inventory_at = now() so the key shows up under Inventory."""
    from datetime import datetime, timezone
    client = get_client()
    res = client.table('mobile_keys').update({
        'moved_to_inventory_at': datetime.now(timezone.utc).isoformat(),
    }).eq('id', key_id).execute()
    return res.data[0] if res.data else None


def clear_mobile_key_inventory(key_id):
    """Clear the inventory flag so the key returns to the active list."""
    client = get_client()
    res = client.table('mobile_keys').update({
        'moved_to_inventory_at': None,
    }).eq('id', key_id).execute()
    return res.data[0] if res.data else None


def set_mobile_key_status(key_id, status_done):
    """Flip the per-row Status checkbox (true = done, false = pending)."""
    client = get_client()
    res = client.table('mobile_keys').update({
        'status_done': bool(status_done),
    }).eq('id', key_id).execute()
    return res.data[0] if res.data else None


def set_mobile_key_ordered(key_id, ordered):
    """Flip the per-row Ordered checkbox."""
    client = get_client()
    res = client.table('mobile_keys').update({
        'ordered': bool(ordered),
    }).eq('id', key_id).execute()
    return res.data[0] if res.data else None


def set_mobile_key_key_code(key_id, key_code, key_code_value=None):
    """Set the per-row Key Code checkbox state plus the entered code text.

    key_code is the checkbox state; key_code_value is the actual key code
    string (None when unchecked / no code entered).
    """
    client = get_client()
    res = client.table('mobile_keys').update({
        'key_code': bool(key_code),
        'key_code_value': key_code_value,
    }).eq('id', key_id).execute()
    return res.data[0] if res.data else None


def set_mobile_key_notes(key_id, notes):
    """Set the per-row free-text note (None clears it).

    Written by the Notes column modal on the list pages; the add/edit form
    writes the same column through update_mobile_key.
    """
    client = get_client()
    res = client.table('mobile_keys').update({
        'notes': notes,
    }).eq('id', key_id).execute()
    return res.data[0] if res.data else None


def list_mobile_keys_in_inventory():
    client = get_client()
    res = (
        client.table('mobile_keys')
        .select('*')
        .not_.is_('moved_to_inventory_at', 'null')
        .order('moved_to_inventory_at', desc=True)
        .execute()
    )
    return res.data or []


# ---------------------------------------------------------------------------
# Key code contacts (Mobile Keys -> Key Code Contacts)
# ---------------------------------------------------------------------------

def list_key_code_contacts():
    """Return all key_code_contacts rows, oldest first (insertion order)."""
    client = get_client()
    res = client.table('key_code_contacts').select('*').order('created_at').execute()
    return res.data or []


def create_key_code_contact(data):
    client = get_client()
    res = client.table('key_code_contacts').insert(data).execute()
    return res.data[0] if res.data else None


def update_key_code_contact(contact_id, data):
    client = get_client()
    res = client.table('key_code_contacts').update(data).eq('id', contact_id).execute()
    return res.data[0] if res.data else None


def delete_key_code_contact(contact_id):
    client = get_client()
    client.table('key_code_contacts').delete().eq('id', contact_id).execute()
