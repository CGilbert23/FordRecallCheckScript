"""Parse the Xtime "Technician RO / ASR Report Totals" export.

Xtime's "Excel" download is really an HTML page saved with a .xls name: one
<div> per store name followed by a table with four rows per technician (RO,
Inspection, ASR, Emailed). The first cell of each RO row carries the tech's
name with rowspan=4, so the row layout is:

    RO row:          name, 'RO', cust, warr, TOTAL RO, %, booklet, AVG MILES,
                     hours req, hours sold, closing %, req per, sold per,
                     LINES REQ, LINES SOLD, ...
    Inspection row:  'Inspection', cust, warr, TOTAL (= MPIs completed), ...
    ASR row:         'ASR', cust, warr, TOTAL (= ROs with an ASR), ...

Each store table ends with a "<store> Totals" block, and the file ends with a
"Fred Beans Totals" section — both are skipped.

Pure module, no Flask import, so it can be run straight from the shell:

    python xtime_tech_report.py "uploadfiles/ASR Report/<file>.xls"
"""

import re
import calendar
from datetime import date
from html.parser import HTMLParser

# The mobile techs pulled out of the company-wide report. `store` is what the
# report page shows; `store_words` must all appear in Xtime's store heading
# (after normalising) so a same-named tech at another store can't be picked
# up. `aliases` covers spellings Xtime uses that differ from ours.
MOBILE_TECHS = [
    {'name': 'Brandon Roberts', 'store': 'Ford Doylestown', 'store_words': ('ford', 'doylestown')},
    {'name': 'Savannah Miller', 'store': 'Lincoln Doylestown', 'store_words': ('lincoln', 'doylestown')},
    {'name': 'Luis Muniz', 'store': 'Ford Newtown', 'store_words': ('ford', 'newtown')},
    {'name': 'Garret Chanin', 'store': 'Ford Washington', 'store_words': ('ford', 'washington')},
    {'name': 'Cameron Lee', 'store': 'Ford Langhorne', 'store_words': ('ford', 'langhorne')},
    {'name': 'Alex Innes', 'store': 'Ford West Chester', 'store_words': ('ford', 'west', 'chester')},
    {'name': 'Scott Ryan', 'store': 'Ford West Chester', 'store_words': ('ford', 'west', 'chester')},
    {'name': 'Gabriel Lackman', 'store': 'Ford Exton', 'store_words': ('ford', 'exton')},
    {'name': 'Antonio Dixon', 'store': 'Ford Mechanicsburg', 'store_words': ('ford', 'mechanicsburg')},
    {'name': 'Bryan Burgos', 'store': 'Ford Mechanicsburg', 'store_words': ('ford', 'mechanicsburg')},
    {'name': 'Grant Carlson', 'store': 'Ford Boyertown', 'store_words': ('ford', 'boyertown')},
]

METRIC_KEYS = ('total_ro', 'mpi_completed', 'avg_miles', 'asr', 'lines_requested', 'lines_sold')

_DATE_RANGE_RE = re.compile(
    r'Date Range:\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*-\s*(\d{1,2})/(\d{1,2})/(\d{4})')


def _norm_name(s):
    return ' '.join((s or '').lower().split())


def _store_words(s):
    return set(re.sub(r'[^a-z]+', ' ', (s or '').lower()).split())


def _int(s):
    """'1,970' / '$1,970.25' / '' -> int or None."""
    s = (s or '').replace('$', '').replace(',', '').replace('%', '').strip()
    try:
        return int(round(float(s))) if s else None
    except ValueError:
        return None


class _ReportHTML(HTMLParser):
    """Flattens the page into ('div', text) and ('row', [cell texts]) events."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events = []
        self._div = None
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'div':
            self._div = []
        elif tag == 'tr':
            self._row = []
        elif tag in ('td', 'th') and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == 'div' and self._div is not None:
            text = ' '.join(''.join(self._div).split())
            if text:
                self.events.append(('div', text))
            self._div = None
        elif tag in ('td', 'th') and self._cell is not None:
            self._row.append(' '.join(''.join(self._cell).split()))
            self._cell = None
        elif tag == 'tr' and self._row is not None:
            self.events.append(('row', self._row))
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        elif self._div is not None:
            self._div.append(data)


def parse_report(data):
    """Parse report bytes into {'period_start', 'period_end', 'techs': [...]}.

    Every tech in the company is returned (not just mobile techs) so a roster
    change later still works against months that were already uploaded.
    Raises ValueError when the file isn't a full-month Technician RO / ASR report.
    """
    text = data.decode('utf-8', errors='replace') if isinstance(data, bytes) else data
    if 'Technician RO / ASR Report' not in text:
        raise ValueError("That doesn't look like an Xtime Technician RO / ASR Report.")

    m = _DATE_RANGE_RE.search(text)
    if not m:
        raise ValueError("Couldn't find the report's date range.")
    sm, sd, sy, em, ed, ey = (int(x) for x in m.groups())
    if not (sd == 1 and (ey, em, ed) == (sy, sm, calendar.monthrange(sy, sm)[1])):
        raise ValueError(
            f'That report covers {sm}/{sd}/{sy} - {em}/{ed}/{ey}. '
            'Only full-month reports (the 1st through the last day) can be uploaded.')

    p = _ReportHTML()
    p.feed(text)

    techs = []
    store = None
    pending = None  # tech whose RO row we've seen, waiting on its Inspection + ASR rows
    for kind, val in p.events:
        if kind == 'div':
            if not val.startswith(('Avg Miles', 'Date Range', 'Technician RO')):
                store = val
            continue
        cells = val
        if pending is not None and cells and cells[0] == 'Inspection':
            pending['mpi_completed'] = _int(cells[3]) if len(cells) > 3 else None
            continue
        if pending is not None and cells and cells[0] == 'ASR':
            pending['asr'] = _int(cells[3]) if len(cells) > 3 else None
            techs.append(pending)
            pending = None
            continue
        if len(cells) < 15 or cells[1] != 'RO':
            continue
        name = cells[0]
        if not name or name.endswith(' Totals') or not store or store == 'Fred Beans Totals':
            continue
        pending = {
            'store': store,
            'name': name,
            'total_ro': _int(cells[4]),
            'avg_miles': _int(cells[7]),
            'lines_requested': _int(cells[13]),
            'lines_sold': _int(cells[14]),
            'mpi_completed': None,
            'asr': None,
        }

    if not techs:
        raise ValueError('No technicians were found in that report.')
    return {'period_start': date(sy, sm, sd), 'period_end': date(ey, em, ed), 'techs': techs}


def _pct(num, den):
    return num / den if den and num is not None else None


def _with_rates(row):
    row['mpi_pct'] = _pct(row.get('mpi_completed'), row.get('total_ro'))
    row['asr_pct'] = _pct(row.get('asr'), row.get('total_ro'))
    return row


def mobile_tech_rows(techs, roster=MOBILE_TECHS):
    """Pick the roster's techs out of a parsed report, in roster order.

    Name match is case/space-insensitive (Xtime has 'BRANDON ROBERTS'). A
    candidate at the roster's store wins; failing that, the name alone is
    accepted so a tech who moved stores still shows (with the store Xtime
    lists). Techs missing from the month come back with found=False.
    """
    by_name = {}
    for t in techs:
        by_name.setdefault(_norm_name(t['name']), []).append(t)

    rows = []
    for r in roster:
        names = [r['name'], *r.get('aliases', ())]
        cands = [t for n in names for t in by_name.get(_norm_name(n), [])]
        want = set(r['store_words'])
        at_store = [t for t in cands if want <= _store_words(t['store'])]
        hit = (at_store or cands or [None])[0]
        row = {'name': r['name'], 'store': r['store'], 'found': hit is not None,
               'report_store': hit['store'] if hit else None,
               'moved': bool(hit) and not at_store}
        for k in METRIC_KEYS:
            row[k] = hit.get(k) if hit else None
        rows.append(_with_rates(row))
    return rows


def team_total(rows):
    """Sum the found rows; Avg Miles is weighted by each tech's RO count."""
    found = [r for r in rows if r['found']]
    tot = {'name': 'Mobile Team', 'store': f"{len(found)} tech{'' if len(found) == 1 else 's'}"}
    for k in ('total_ro', 'mpi_completed', 'asr', 'lines_requested', 'lines_sold'):
        tot[k] = sum(r[k] or 0 for r in found)
    weighted = [(r['avg_miles'], r['total_ro']) for r in found if r['avg_miles'] and r['total_ro']]
    ro = sum(w for _, w in weighted)
    tot['avg_miles'] = round(sum(m * w for m, w in weighted) / ro) if ro else None
    return _with_rates(tot)


if __name__ == '__main__':
    import sys
    with open(sys.argv[1], 'rb') as fh:
        parsed = parse_report(fh.read())
    print(f"{parsed['period_start']} - {parsed['period_end']}: {len(parsed['techs'])} techs")
    rows = mobile_tech_rows(parsed['techs'])

    def fmt(v):
        return '-' if v is None else (f'{v:.0%}' if isinstance(v, float) else v)

    for r in rows + [team_total(rows)]:
        print(f"{r['name']:<18} {(r.get('report_store') or r['store'])[:30]:<30} "
              + ' '.join(f'{fmt(r[k]):>6}' for k in (
                  'total_ro', 'mpi_completed', 'mpi_pct', 'avg_miles', 'asr', 'asr_pct',
                  'lines_sold')))
