"""Parse Ford's weekly mobile-service KPI export and build the KPI Tracker rows.

Ford emails an .xlsx every Monday covering the current month to date, two
days behind (the "August 3" file is all of July; the "August 24" file is
Aug 1-21). Layout, one sheet:

    row 1:  month labels ('Jul', or 'Jan'..'Dec' in the 2025 full-year file),
            merged across each month's block in 2026 files; the last block is
            'Total' (a repeat of the file's range) and is skipped
    row 2:  headers — Dealer Region, CVC Dlr, Dlr P&A Code, Dlr Name, then the
            same ~45 KPI columns repeated once per month block
    rows 3+: one row per store

Columns are matched by (normalised) header name, never position — 2026
dropped the 2025 'Enrolled Dealers' column. Every column is kept raw so a
metric Ford adds later is already stored.

The file has no day count or year. Days elapsed is backed out of Ford's own
ROs/Van/Day (CX Count / Reporting Vans / ROs/Van/Day comes out a clean
integer — 22 for July 2026); the year comes from the date in the filename.

Pure module, no Flask import, so it can be run straight from the shell:

    python kpi_tracker.py "uploadfiles/KPI Report/<file>.xlsx"
"""

import io
import re
import calendar
import statistics
from datetime import date, timedelta

import openpyxl

# The stores, in the order the report shows them. `techs` / `offset_value`
# seed each new month's editable settings (a new month copies the previous
# month's settings when there is one, so these only matter for the first).
STORES = [
    {'code': '01273', 'name': 'Ford Boyertown', 'techs': 2, 'offset_value': 150},
    {'code': '01341', 'name': 'Ford West Chester', 'techs': 2, 'offset_value': 160},
    {'code': '04197', 'name': 'Ford Mechanicsburg', 'techs': 2, 'offset_value': 160},
    {'code': '01305', 'name': 'Ford Langhorne', 'techs': 1, 'offset_value': 140},
    {'code': '01203', 'name': 'Ford Doylestown', 'techs': 1, 'offset_value': 150},
    {'code': '01017', 'name': 'Ford Exton', 'techs': 1, 'offset_value': 130},
    {'code': '01844', 'name': 'Ford Newtown', 'techs': 1, 'offset_value': 140},
    {'code': '05494', 'name': 'Ford Washington', 'techs': 1, 'offset_value': 120},
    {'code': '11524', 'name': 'Lincoln Doylestown', 'techs': 1, 'offset_value': 170},
]
STORE_BY_CODE = {s['code']: s for s in STORES}

# Offset-eligible ROs per launched van per month (always the full month).
OFFSET_ROS_PER_VAN = 138
# Ford's Ford Pro share understates the commercial work, so the report adds
# 5 points to it.
COMMERCIAL_MIX_BUMP = 0.05

# Normalised header keys (see _norm_header) for the columns the report uses.
K_REGION = 'dealer region'
K_CODE = 'dlr p & a code'
K_NAME = 'dlr name'
K_CX = 'cx count'
K_TOTAL_RO = 'total ro'
K_LAUNCHED_VANS = 'launched vans'
K_REPORTING_VANS = 'reporting vans'
K_ROS_VAN_DAY = 'ros van day'
K_HOURS = 'ms labor hours'
K_CP_HOURS = 'labor hours cp'
K_FORD_PRO = 'ford pro count'
K_REVENUE = 'total revenue $'
K_VISIT_DOLLARS = '60 day dealer visit total dollars'

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
_FILENAME_DATE_RE = re.compile(r'([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(20\d{2})')
_FILENAME_YEAR_RE = re.compile(r'(?<!\d)(20\d{2})(?!\d)')


def _norm_header(h):
    """'Dealer Net (Parts) ( $ )_x000D_\\n' -> 'dealer net parts $'."""
    s = re.sub(r'_x000d_', ' ', str(h or ''), flags=re.I)
    s = re.sub(r'([%$&])', r' \1 ', s.lower())
    return ' '.join(re.sub(r'[^a-z0-9%$&]+', ' ', s).split())


def _value(v):
    """Ford writes '-' for n/a; keep numbers as numbers and text as text."""
    if isinstance(v, str):
        v = v.strip()
        return None if v in ('', '-') else v
    return v


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _code(v):
    s = str(v).strip() if v is not None else ''
    return s.zfill(5) if s.isdigit() else s


# ---------------------------------------------------------------------------
# Working days
# ---------------------------------------------------------------------------

def _observed(d):
    """Saturday holidays are observed Friday, Sunday ones Monday."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _nth_weekday(year, month, weekday, n):
    """n-th `weekday` (0=Mon) of the month; n=-1 for the last one."""
    days = [date(year, month, d) for d in range(1, calendar.monthrange(year, month)[1] + 1)
            if date(year, month, d).weekday() == weekday]
    return days[n] if n < 0 else days[n - 1]


def holidays(year):
    """Days Ford leaves out of its working-day count.

    Inferred from the 2025 file's day counts: New Year's, Memorial Day,
    July 4, Labor Day, Thanksgiving (not the Friday after) and Dec 24-26.
    Presidents' Day, Juneteenth and Columbus Day are working days.
    """
    days = {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 5, 0, -1),
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _observed(date(year + 1, 1, 1)),  # can land on Dec 31
    }
    days.update(date(year, 12, d) for d in (24, 25, 26))
    return {d for d in days if d.year == year and d.weekday() < 5}


def work_days(year, month, through=None):
    """Working days from the 1st through `through` (default: month end)."""
    last = calendar.monthrange(year, month)[1]
    end = min(through.day, last) if through else last
    off = holidays(year)
    return sum(1 for d in range(1, end + 1)
               if date(year, month, d).weekday() < 5 and date(year, month, d) not in off)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _reference_date(filename, today):
    """(date, full_year): the date the file speaks for, used to put a year on
    its month labels and to tell finished months from the one in progress.

    A full date in the name ('Untitled - August 3, 2026') is the send date. A
    bare year ('FredBeans_2025') is a year file: every month is that year, and
    a month counts as finished once it has ended.
    """
    m = _FILENAME_DATE_RE.search(filename or '')
    if m and m.group(1)[:3].lower() in _MONTHS:
        try:
            return date(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2))), False
        except ValueError:
            pass
    m = _FILENAME_YEAR_RE.search(filename or '')
    if m:
        return date(int(m.group(1)), 12, 31), True
    return today, False


def _days_elapsed(stores):
    """Back the day count out of Ford's ROs/Van/Day (median across stores)."""
    counts = []
    for s in stores:
        raw = s['raw']
        cx, vans, rvd = _num(raw.get(K_CX)), _num(raw.get(K_REPORTING_VANS)), _num(raw.get(K_ROS_VAN_DAY))
        if cx and vans and rvd:
            counts.append(cx / vans / rvd)
    return round(statistics.median(counts)) if counts else None


def parse_report(data, filename='', today=None):
    """Parse the KPI .xlsx bytes into one dict per month block:

        {'period_start': date, 'days_elapsed': int, 'work_days': int,
         'complete': bool, 'columns': {key: original header},
         'stores': [{'code', 'name', 'region', 'raw': {key: value}}]}

    Raises ValueError when the file isn't Ford's KPI export.
    """
    today = today or date.today()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise ValueError("That file couldn't be opened as an Excel workbook.")
    try:
        rows = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    finally:
        wb.close()

    hdr_i = next((i for i, r in enumerate(rows) if K_CODE in [_norm_header(c) for c in r]), None)
    if not hdr_i:
        raise ValueError("That doesn't look like Ford's KPI report (no 'Dlr P&A Code' column).")
    headers = [_norm_header(c) for c in rows[hdr_i]]
    labels = rows[hdr_i - 1] + [None] * (len(headers) - len(rows[hdr_i - 1]))

    # Forward-fill the (merged) month labels and group columns into blocks.
    ident = {h: i for i, h in enumerate(headers[:headers.index(K_CX)])}
    blocks, current = [], None
    for i in range(len(ident), len(headers)):
        label = str(labels[i]).strip() if labels[i] not in (None, '') else None
        if label and (current is None or label != current['label']):
            current = {'label': label, 'cols': []}
            blocks.append(current)
        if current and headers[i]:
            current['cols'].append(i)
    month_blocks = [b for b in blocks if b['label'][:3].lower() in _MONTHS]
    if not month_blocks:
        raise ValueError("Couldn't find any month columns in that report.")

    store_rows = [r for r in rows[hdr_i + 1:] if r and _code(r[ident[K_CODE]])]
    ref, full_year = _reference_date(filename, today)

    months = []
    for b in month_blocks:
        month = _MONTHS[b['label'][:3].lower()]
        year = ref.year - 1 if month > ref.month else ref.year
        if K_CX not in [headers[i] for i in b['cols']]:
            raise ValueError(f"The {b['label']} columns are missing 'CX Count'.")
        region = None
        stores = []
        for r in store_rows:
            r = r + [None] * (len(headers) - len(r))
            region = _value(r[ident[K_REGION]]) if K_REGION in ident and r[ident[K_REGION]] else region
            stores.append({
                'code': _code(r[ident[K_CODE]]),
                'name': _value(r[ident[K_NAME]]) if K_NAME in ident else None,
                'region': region,
                'raw': {headers[i]: _value(r[i]) for i in b['cols']},
            })
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        # A year file (FredBeans_2026) may end with the month still in progress.
        complete = (month_end < today) if full_year else ref > month_end
        full = work_days(year, month)
        days = _days_elapsed(stores)
        if days is None:
            # Nobody has an RO yet — fall back to the calendar. A Monday
            # file runs through the Friday before it.
            days = full if complete else work_days(year, month, ref - timedelta(days=3))
        # A finished month's day count is Ford's, whatever our holiday list says.
        total_days = days if complete else max(full, days)
        months.append({
            'period_start': date(year, month, 1),
            'as_of': ref,  # the Monday the file was sent: the scorecard's column
            # A scorecard week column only makes sense for a weekly file dated
            # inside the month it covers. A year file (every month at once) and
            # the file that closes out the prior month aren't weeks.
            'weekly': not full_year and (ref.year, ref.month) == (year, month),
            'days_elapsed': days,
            'work_days': total_days,
            'complete': complete,
            'columns': {headers[i]: str(rows[hdr_i][i]).replace('_x000D_', '').strip()
                        for i in b['cols']},
            'stores': stores,
        })
    return months


# ---------------------------------------------------------------------------
# Report rows
# ---------------------------------------------------------------------------

def default_settings():
    return {s['code']: {'active_techs': s['techs'], 'offset_value': s['offset_value']} for s in STORES}


def _setting(settings, code, key):
    val = ((settings or {}).get(code) or {}).get(key)
    if val is None:
        base = STORE_BY_CODE.get(code) or {}
        val = base.get('techs' if key == 'active_techs' else 'offset_value', 0)
    return val


# ROs close late in the month — there's always a push in the last two weeks —
# so a straight day-share projection reads low. The bump applies only to the
# part of the month that hasn't happened yet, so it fades to nothing as the
# month closes out (and is zero once the month is finished). 25% on the
# remainder works out to about +9.5% at 13 of 21 days, which is the ~10% the
# team was adding by hand. Replace it with measured numbers once
# `kpi_report_weeks` has a few months of history.
LATE_CLOSE_UPLIFT = 0.25


def projection_factor(days, work_days):
    """Multiplier turning a month-to-date figure into a projected month end."""
    if not days or not work_days:
        return None
    remaining = max(0, work_days - days) / work_days
    return work_days / days * (1 + LATE_CLOSE_UPLIFT * remaining)


def _tracking(ro, days, total_days):
    factor = projection_factor(days, total_days)
    return None if factor is None else int(round(ro * factor, -1))


def _components(store, settings, days, total_days):
    """The additive building blocks of one store-month. Every displayed
    metric (a store, a total, a year) is derived from sums of these."""
    raw = store['raw']
    ro = _num(raw.get(K_CX)) or 0
    units = _num(raw.get(K_LAUNCHED_VANS)) or 0
    techs = _setting(settings, store['code'], 'active_techs') or 0
    offset_value = _setting(settings, store['code'], 'offset_value') or 0
    available = OFFSET_ROS_PER_VAN * units
    return {
        'units': units,
        'techs': techs,
        'offset_value': offset_value,
        'available': available,
        'ro': ro,
        'tracking': _tracking(ro, days, total_days) or 0,
        'hours': _num(raw.get(K_HOURS)) or 0,
        'cp_hours': _num(raw.get(K_CP_HOURS)) or 0,
        'ford_pro': _num(raw.get(K_FORD_PRO)) or 0,
        'ro_value': _num(raw.get(K_REVENUE)) or 0,
        'dealer_ro': _num(raw.get(K_TOTAL_RO)) or 0,
        'total_offset': ro * offset_value,
        'offset_left': max(0, available - ro) * offset_value,
        'visit_spend': _num(raw.get(K_VISIT_DOLLARS)) or 0,
        'tech_days': techs * days,
        'days': days,
    }


_SUMMED = ('units', 'techs', 'available', 'ro', 'tracking', 'hours', 'cp_hours', 'ford_pro',
           'ro_value', 'dealer_ro', 'total_offset', 'offset_left', 'visit_spend', 'tech_days')


def _combine(parts, days, units=None, techs=None, offset_value=None):
    """Sum components. `days` is the combined day count (the month's days
    across stores, the sum of months' days across a year). Units/techs/offset
    value are summed unless given (a year row shows the latest month's)."""
    out = {k: sum(p[k] for p in parts) for k in _SUMMED}
    out['days'] = days
    out['offset_value'] = offset_value
    if units is not None:
        out['units'] = units
    if techs is not None:
        out['techs'] = techs
    return out


def _div(a, b):
    return a / b if b else None


def _derive(c):
    """Components -> the displayed metrics."""
    return {
        'units': c['units'],
        'techs': c['techs'],
        'offset_value': c['offset_value'],
        'available': c['available'],
        'ro': c['ro'],
        'tracking': c['tracking'],
        'hours': c['hours'],
        'cp_hours': c['cp_hours'],
        'commercial_mix': (c['ford_pro'] / c['ro'] + COMMERCIAL_MIX_BUMP) if c['ro'] else None,
        'avg_ro': _div(c['ro_value'], c['ro']),
        'hours_tech_day': _div(c['hours'], c['tech_days']),
        'ro_value': c['ro_value'],
        'pct_total_ro': _div(c['ro'], c['dealer_ro']),
        'total_offset': c['total_offset'],
        'total_revenue': c['ro_value'] + c['total_offset'],
        'ros_tech_day': _div(c['ro'], c['tech_days']),
        'rev_tech_day': _div(c['ro_value'], c['tech_days']),
        'offset_earned': _div(c['ro'], c['available']),
        'offset_left': c['offset_left'],
        'visit_spend': c['visit_spend'],
        'ros_per_day': _div(c['ro'], c['days']),
    }


def _store_name(code, ford_name=None):
    """Our short name for the store; Ford's name title-cased for one we don't know."""
    return (STORE_BY_CODE.get(code) or {}).get('name') or (ford_name or code).title()


def _ordered(stores):
    """The file's stores in STORES order; stores we don't know go last."""
    order = {s['code']: i for i, s in enumerate(STORES)}
    return sorted(stores, key=lambda s: order.get(s['code'], len(order)))


def month_view(report, codes=None):
    """(rows, total) for one saved month. `codes` narrows to those stores."""
    days, total_days = report['days_elapsed'], report['work_days']
    rows, parts = [], []
    for s in _ordered(report.get('stores') or []):
        if codes and s['code'] not in codes:
            continue
        c = _components(s, report.get('settings'), days, total_days)
        parts.append(c)
        rows.append({'code': s['code'], 'dlr_name': s.get('name'),
                     'name': _store_name(s['code'], s.get('name')),
                     **_derive(c)})
    total = _derive(_combine(parts, days)) if parts else None
    return rows, total


def year_view(reports, codes=None):
    """(rows, total) summed across a year's saved months (oldest first).
    Units, techs and offset value show the latest month's settings."""
    by_store, names, days = {}, {}, 0
    for rep in sorted(reports, key=lambda r: str(r['period_start'])):
        days += rep['days_elapsed']
        for s in rep.get('stores') or []:
            if codes and s['code'] not in codes:
                continue
            by_store.setdefault(s['code'], []).append(
                _components(s, rep.get('settings'), rep['days_elapsed'], rep['work_days']))
            names[s['code']] = s.get('name')
    rows, store_totals = [], []
    for s in _ordered([{'code': c} for c in by_store]):
        parts = by_store[s['code']]
        last = parts[-1]
        c = _combine(parts, sum(p['days'] for p in parts),
                     units=last['units'], techs=last['techs'], offset_value=last['offset_value'])
        store_totals.append(c)
        rows.append({'code': s['code'], 'dlr_name': names[s['code']],
                     'name': _store_name(s['code'], names[s['code']]),
                     **_derive(c)})
    total = _derive(_combine(store_totals, days)) if store_totals else None
    return rows, total


# Profitability map thresholds on Total RO Value (no offset), by the store's
# active techs that month: 1 tech 18k/14k, 2 techs 30k/26k, +12k per tech after.
PROFIT_GREEN_BASE = 6000
PROFIT_YELLOW_BASE = 2000
PROFIT_PER_TECH = 12000


def profit_thresholds(techs):
    """(green floor, yellow floor) for a store running `techs` techs."""
    return (PROFIT_GREEN_BASE + PROFIT_PER_TECH * techs,
            PROFIT_YELLOW_BASE + PROFIT_PER_TECH * techs)


def profit_band(value, techs):
    """'green' / 'yellow' / 'red', or None when there's nothing to judge."""
    if not techs or value is None:
        return None
    green, yellow = profit_thresholds(techs)
    return 'green' if value >= green else 'yellow' if value >= yellow else 'red'


def profitability_view(reports):
    """Year profitability map: one row per store, one cell per month.

    Each cell carries that month's Total RO Value (no offset) and the techs it
    is judged against. A month still in progress is flagged `partial` and left
    unbanded — a part-month total would always read red.

    Returns (rows, totals, months_present).
    """
    by_store, names, months_present, latest = {}, {}, [], {}
    for rep in sorted(reports, key=lambda r: str(r['period_start'])):
        month = int(str(rep['period_start'])[5:7])
        months_present.append(month)
        partial = not _is_complete(rep)
        for s in rep.get('stores') or []:
            c = _components(s, rep.get('settings'), rep['days_elapsed'], rep['work_days'])
            by_store.setdefault(s['code'], {})[month] = {
                'value': c['ro_value'],
                'techs': c['techs'],
                'partial': partial,
                'band': None if partial else profit_band(c['ro_value'], c['techs']),
            }
            names[s['code']] = s.get('name')
            latest[s['code']] = c  # reports are oldest first, so this ends up newest

    rows = []
    for s in _ordered([{'code': c} for c in by_store]):
        code = s['code']
        cells = by_store[code]
        rows.append({'code': code, 'name': _store_name(code, names.get(code)),
                     'units': latest[code]['units'], 'techs': latest[code]['techs'],
                     'months': cells,
                     'total': sum(m['value'] for m in cells.values())})
    totals = {'months': {m: {'value': sum(r['months'][m]['value'] for r in rows if m in r['months']),
                             'partial': any(r['months'][m]['partial'] for r in rows if m in r['months'])}
                         for m in months_present},
              'total': sum(r['total'] for r in rows),
              'units': sum(r['units'] for r in rows),
              'techs': sum(r['techs'] for r in rows)}
    return rows, totals, months_present


YOY_METRICS = ('ro', 'avg_ro', 'commercial_mix', 'total_revenue', 'total_offset')


def _is_complete(report):
    return report['days_elapsed'] >= report['work_days']


def _scaled(c, factor):
    return {k: (v * factor if k in _SUMMED else v) for k, v in c.items()}


def _yoy_metrics(parts):
    d = _derive(_combine(parts, 0))
    return {k: d[k] for k in YOY_METRICS}


def _yoy_changes(cur, prev):
    out = {}
    for k in YOY_METRICS:
        a, b = cur.get(k), prev.get(k)
        if a is None or b is None:
            out[k] = None
        elif k == 'commercial_mix':
            out[k] = a - b  # percentage points
        else:
            out[k] = (a - b) / b if b else None
    return out


def yoy_view(cur_reports, prior_reports, codes=None):
    """Year-over-year for the months in `cur_reports` that the prior year also
    has. Returns (rows, total, months_compared, pace) or None when there's
    nothing to compare.

    A month still in progress is compared at the same pace: the prior year's
    additive numbers (RO count, revenue, ...) are scaled by days elapsed /
    working days, so 8 of 21 days is measured against 8/21 of last year's
    month. `pace` is (days_elapsed, work_days) when that happened.
    """
    prior_by_month = {str(r['period_start'])[5:7]: r for r in prior_reports}
    cur, prev, names, months, pace = {}, {}, {}, 0, None
    for rep in cur_reports:
        p = prior_by_month.get(str(rep['period_start'])[5:7])
        if not p:
            continue
        months += 1
        factor = 1.0
        if not _is_complete(rep):
            factor = rep['days_elapsed'] / rep['work_days']
            pace = (rep['days_elapsed'], rep['work_days'])
        for side, r, f in ((cur, rep, 1.0), (prev, p, factor)):
            for s in r.get('stores') or []:
                if codes and s['code'] not in codes:
                    continue
                c = _components(s, r.get('settings'), r['days_elapsed'], r['work_days'])
                side.setdefault(s['code'], []).append(_scaled(c, f))
                names.setdefault(s['code'], s.get('name'))
    if not months:
        return None
    rows, cur_all, prev_all = [], [], []
    for s in _ordered([{'code': c} for c in set(cur) | set(prev)]):
        code = s['code']
        cur_all += cur.get(code, [])
        prev_all += prev.get(code, [])
        now, then = _yoy_metrics(cur.get(code, [])), _yoy_metrics(prev.get(code, []))
        rows.append({'code': code, 'name': _store_name(code, names.get(code)),
                     'cur': now, 'prev': then, 'change': _yoy_changes(now, then)})
    now, then = _yoy_metrics(cur_all), _yoy_metrics(prev_all)
    total = {'cur': now, 'prev': then, 'change': _yoy_changes(now, then)}
    return rows, total, months, pace


# ---------------------------------------------------------------------------
# EOS Scorecard
# ---------------------------------------------------------------------------

# Green within 10% of goal, yellow 10-20% under, red more than 20% under.
SCORECARD_GREEN = 0.90
SCORECARD_YELLOW = 0.80

# Rows, in the order the team's spreadsheet lists them. `rate` rows are per-day
# or per-RO figures — they're compared to the goal as-is (no pacing) and have
# no month-end projection. `manual` rows take their Tracking by hand (vans on
# order, techs being hired). The per-store RO rows are inserted after 'ro'.
SCORECARD_SECTIONS = [
    {'title': 'Vans & Technicians', 'rows': [
        {'key': 'vans', 'label': 'Van Count', 'fmt': 'int', 'manual': True},
        {'key': 'techs', 'label': 'Active Mobile Technicians', 'fmt': 'int', 'manual': True},
    ]},
    {'title': 'KPI', 'rows': [
        {'key': 'ro', 'label': 'Total RO Count', 'fmt': 'int', 'stores': True},
        # Goal calculated from the Total RO Count goal, the way the team's
        # spreadsheet does it: 1120 / 21 working days = 53.3.
        {'key': 'ro_per_day', 'label': 'Avg RO Per Day', 'fmt': 'dec', 'rate': True,
         'derived': True, 'gap': True},
        # Goal calculated: RO Count goal / techs goal / working days (1120/12/21 = 4.4).
        {'key': 'ro_per_tech_day', 'label': 'RO Per Active Tech / Day', 'fmt': 'dec',
         'rate': True, 'derived': True},
        {'key': 'avg_ro_value', 'label': 'Avg RO Value', 'fmt': 'money', 'rate': True},
        # Goal calculated: RO Count goal x Avg RO Value goal (1120 x 160).
        {'key': 'revenue', 'label': 'Total Revenue', 'fmt': 'money', 'derived': True, 'gap': True},
        {'key': 'commercial_mix', 'label': 'Commercial Mix', 'fmt': 'pct', 'rate': True},
    ]},
]


def derived_goals(goals, year, month):
    """Fill in the goals the spreadsheet calculates rather than types."""
    goals = dict(goals or {})
    days = work_days(year, month)
    if goals.get('ro') and days:
        goals['ro_per_day'] = goals['ro'] / days
        if goals.get('techs'):
            goals['ro_per_tech_day'] = goals['ro'] / goals['techs'] / days
    if goals.get('ro') and goals.get('avg_ro_value'):
        goals['revenue'] = goals['ro'] * goals['avg_ro_value']
    return goals


# The team's starting goals — what a month shows before anything is saved and
# there's no earlier scorecard to copy from. Edit them on the page per month.
DEFAULT_SCORECARD_GOALS = {
    'vans': 16, 'techs': 12,
    'ro': 1120,
    'store:01273': 180,   # Boyertown
    'store:01341': 170,   # West Chester
    'store:04197': 140,   # Mechanicsburg
    'store:01017': 120,   # Exton
    'store:01305': 120,   # Langhorne
    'store:01203': 120,   # Doylestown
    'store:05494': 90,    # Washington
    'store:01844': 90,    # Newtown
    'store:11524': 90,    # Lincoln Doylestown
    'avg_ro_value': 160, 'commercial_mix': 0.40,
    # Avg RO Per Day, RO Per Active Tech / Day and Total Revenue are
    # calculated — see derived_goals().
}


def mondays(year, month):
    """Every Monday in the month — the scorecard's week columns. Ford's file
    lands on a Monday and covers through the Friday before."""
    last = calendar.monthrange(year, month)[1]
    return [date(year, month, d) for d in range(1, last + 1)
            if date(year, month, d).weekday() == 0]


def goal_band(value, goal):
    """'green' / 'yellow' / 'red' against a goal (or a pace-adjusted goal)."""
    if value is None or not goal:
        return None
    ratio = value / goal
    return ('green' if ratio >= SCORECARD_GREEN
            else 'yellow' if ratio >= SCORECARD_YELLOW else 'red')


def _scorecard_metrics(snapshot, settings):
    """One snapshot (a weekly upload or the finished month) -> {row key: value},
    plus the same projected to month end for the additive rows."""
    days, total = snapshot['days_elapsed'], snapshot['work_days']
    parts, per_store = [], {}
    for s in snapshot.get('stores') or []:
        c = _components(s, settings, days, total)
        parts.append(c)
        per_store[s['code']] = c
    c = _combine(parts, days)
    actual = {
        'vans': c['units'],
        'techs': c['techs'],
        'ro': c['ro'],
        'ro_per_day': _div(c['ro'], days),
        'ro_per_tech_day': _div(c['ro'], c['tech_days']),
        'revenue': c['ro_value'],
        'avg_ro_value': _div(c['ro_value'], c['ro']),
        'commercial_mix': (c['ford_pro'] / c['ro'] + COMMERCIAL_MIX_BUMP) if c['ro'] else None,
    }
    for code, sc in per_store.items():
        actual['store:' + code] = sc['ro']
    factor = projection_factor(days, total)
    tracking = {k: (v * factor if v is not None and factor else None)
                for k, v in actual.items()
                if k in ('ro', 'revenue') or k.startswith('store:')}
    return {'actual': actual, 'tracking': tracking, 'days': days, 'work_days': total,
            'stores': per_store, 'complete': _is_complete(snapshot)}


def scorecard_view(period_start, weeks, month_report, settings=None, goals=None, manual=None):
    """Build the EOS Scorecard grid for one month.

    `weeks` are `kpi_report_weeks` rows (one per Monday upload), `month_report`
    the `kpi_reports` row (used for the EOM column once the month is finished).
    Columns are every Monday in the month plus EOM; a week with no upload is
    blank. Actuals are banded against the goal scaled to the days elapsed, so
    a part-month reads as on-pace or not; Tracking is banded against the full
    goal. Rate rows (per day, per RO) are banded against the goal as-is.
    """
    start = period_start if isinstance(period_start, date) else _parse_date(period_start)
    goals, manual = derived_goals(goals, start.year, start.month), manual or {}
    by_week = {}
    for w in weeks:
        m = _scorecard_metrics(w, settings)
        by_week[str(w['as_of'])[:10]] = m
    latest = max(by_week.values(), key=lambda m: m['days'], default=None)

    columns = []
    for monday in mondays(start.year, start.month):
        key = monday.isoformat()
        columns.append({'key': key, 'label': f'{monday.day}-{calendar.month_abbr[monday.month]}',
                        'metrics': by_week.get(key), 'manual': (manual or {}).get(key) or {}})
    eom = _scorecard_metrics(month_report, settings) if month_report and _is_complete(month_report) else None

    sections = []
    for section in SCORECARD_SECTIONS:
        rows = []
        for spec in section['rows']:
            rows.append(_scorecard_row(spec, spec['key'], spec['label'], columns, eom, goals))
            if spec.get('stores'):
                # Before the month's first upload there's nothing to read the
                # roster from, so fall back to the store list — the goals still
                # need a row to be typed into.
                known = latest['stores'] if latest else {}
                for s in _ordered([{'code': c} for c in (known or STORE_BY_CODE)]):
                    code = s['code']
                    rows.append(_scorecard_row({'fmt': 'int', 'store': True}, 'store:' + code,
                                               _store_name(code), columns, eom, goals))
        sections.append({'title': section['title'], 'rows': rows})
    return {'columns': columns, 'sections': sections, 'has_data': bool(by_week)}


def _scorecard_row(spec, key, label, columns, eom, goals):
    goal = goals.get(key)
    try:
        goal = float(goal) if goal not in (None, '') else None
    except (TypeError, ValueError):
        goal = None
    cells = []
    for col in columns:
        m = col['metrics']
        cell = {'actual': None, 'tracking': None, 'band': None, 'tracking_band': None}
        if spec.get('manual'):
            cell['tracking'] = col['manual'].get(key)
            cell['manual'] = True
        if m:
            cell['actual'] = m['actual'].get(key)
            if spec.get('manual'):
                # Counts of vans and techs: what's there is there, no pacing.
                cell['band'] = goal_band(cell['actual'], goal)
            else:
                cell['tracking'] = m['tracking'].get(key)
                cell['tracking_band'] = goal_band(cell['tracking'], goal)
                # A rate (per day, per RO) is already comparable to the goal;
                # a running total is judged by where it's heading, so Actual
                # and Tracking always carry the same colour.
                cell['band'] = (goal_band(cell['actual'], goal) if spec.get('rate')
                                else cell['tracking_band'])
        cells.append(cell)
    eom_value = eom['actual'].get(key) if eom else None
    return {'key': key, 'label': label, 'fmt': spec.get('fmt', 'int'), 'goal': goal,
            'cells': cells, 'eom': eom_value, 'eom_band': goal_band(eom_value, goal),
            'rate': bool(spec.get('rate')), 'manual': bool(spec.get('manual')),
            'derived': bool(spec.get('derived')),
            'store': bool(spec.get('store')), 'gap': bool(spec.get('gap'))}


def _parse_date(value):
    return date(*(int(p) for p in str(value)[:10].split('-')))


if __name__ == '__main__':
    import sys
    with open(sys.argv[1], 'rb') as fh:
        months = parse_report(fh.read(), sys.argv[1])
    for m in months:
        m['settings'] = default_settings()
        print(f"\n{m['period_start']:%B %Y}: {m['days_elapsed']} of {m['work_days']} working days"
              f"{' (complete)' if m['complete'] else ''}, {len(m['stores'])} stores")
        rows, total = month_view(m)

        def f(v, kind):
            if v is None:
                return '-'
            return {'pct': f'{v:.0%}', 'money': f'${v:,.0f}', 'dec': f'{v:.1f}'}.get(kind, f'{v:,.0f}')

        cols = [('units', ''), ('techs', ''), ('ro', ''), ('tracking', ''), ('commercial_mix', 'pct'),
                ('avg_ro', 'money'), ('ros_tech_day', 'dec'), ('hours_tech_day', 'dec'),
                ('rev_tech_day', 'money'), ('total_revenue', 'money'),
                ('offset_earned', 'pct'), ('offset_left', 'money'), ('visit_spend', 'money')]
        print(f"{'Store':<20}" + ''.join(f'{k[:9]:>10}' for k, _ in cols))
        for r in rows + [dict(total, name='TOTAL')]:
            print(f"{r['name']:<20}" + ''.join(f'{f(r[k], kind):>10}' for k, kind in cols))
        print(f"{total['ros_per_day']:.0f} ROs/day")
