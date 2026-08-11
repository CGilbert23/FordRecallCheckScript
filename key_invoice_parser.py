"""Parse CDK parts invoices (Fred Beans Parts) into key part numbers + costs.

Pure module — no Flask import — so it can be exercised straight from the shell:

    python -c "import key_invoice_parser as p; \
        print(p.parse_invoice_pdf(open('KeyDash/316120.pdf','rb').read())['groups'])"

Invoice shape: each printed line item is three text lines,

    1   1  0 69515-06030         KEY, MASTER   36.58  24.19      24.19
                3TMDZ5BN5PM142090                 <- VIN
                316115                            <- RO number

Columns are ORD / SHIP / O.O. / PART NUMBER / DESCRIPTION / LIST / NET / AMOUNT.
NET is the cost we record; LIST is MSRP and is discarded. The part number we
want is always the PART NUMBER column, never the number that sometimes shows up
inside the description (Ford lines read `5923694 | 164R8134 KEY`).

Two quirks the parser has to survive:
  * CDK prints a CUSTOMER COPY and an OFFICE COPY of the same content on one
    physical page, so every block extracts twice. See _dedupe_items.
  * One RO can cover several VINs, and one (VIN, RO) group can straddle a page
    break — so grouping keys on the pair, never on RO alone.
"""

import io
import re

# ORD SHIP O.O. PART DESCRIPTION LIST NET AMOUNT. Anchored on the three trailing
# money columns rather than column offsets — the description column start shifts
# from invoice to invoice.
RE_LINE_ITEM = re.compile(
    r'^\s*(?P<qty>\d+)\s+(?P<ship>\d+)\s+(?P<oo>\d+)\s+'
    r'(?P<part>\S+)\s+'
    r'(?P<desc>.*?)\s+'
    r'(?P<list>[\d,]+\.\d{2})\s+'
    r'(?P<net>[\d,]+\.\d{2})\s+'
    r'(?P<amount>[\d,]+\.\d{2})\s*$'
)
RE_VIN = re.compile(r'^\s*(?P<vin>[A-HJ-NPR-Z0-9]{17})\s*$')  # VIN charset drops I/O/Q
RE_RO = re.compile(r'^\s*(?P<ro>\d{4,8})\s*$')
RE_REPLACES = re.compile(r'^\s*Part number\s')   # "Part number X replaces Y" — skip, keep the item open
RE_MONEY_TOTAL = re.compile(r'\$([\d,]+\.\d{2})')
SENTINEL = 'ACCOUNT NO.'


def _to_float(raw):
    try:
        return float(str(raw).replace(',', '').replace('$', '').strip())
    except (TypeError, ValueError):
        return None


def extract_text_pages(pdf_bytes):
    """PDF bytes -> one text string per page.

    The only place the PDF library is touched, so swapping extractors is a
    one-function edit. `layout` mode is required: the default mode collapses the
    item line, VIN and RO onto a single line.
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return [page.extract_text(extraction_mode='layout') or '' for page in reader.pages]


def _dedupe_items(items, sentinel_count, page_no, warnings):
    """Drop the OFFICE COPY half of a page's line items.

    Only halves when both signals agree: the page carried two copy headers AND
    the item list is an exact positional 2x repetition. Positional (not
    set-based) so a genuinely repeated line on a one-copy invoice survives.
    """
    if sentinel_count < 2:
        return items
    half = len(items) // 2
    if half and len(items) % 2 == 0 and items[:half] == items[half:]:
        return items[:half]
    warnings.append(
        f"Page {page_no}: looked like a two-copy page but the line items "
        f"didn't repeat evenly ({len(items)} found) — nothing was de-duplicated."
    )
    return items


def parse_line_items(page_texts):
    """Page texts -> (line items, warnings).

    Each item is {'part_number', 'description', 'net', 'amount', 'qty', 'vin',
    'ro_number'}. VIN and RO are only ever read while an item is open, which is
    what keeps the loose RO pattern from swallowing stray numbers elsewhere on
    the page.
    """
    items = []
    warnings = []

    for page_no, text in enumerate(page_texts, start=1):
        lines = [ln for ln in text.split('\n') if ln.strip()]
        sentinel_count = sum(1 for ln in lines if SENTINEL in ln)
        page_items = []
        current = None

        def flush():
            if current is not None and current['vin'] and current['ro_number']:
                page_items.append(current)

        for line in lines:
            m = RE_LINE_ITEM.match(line)
            if m:
                flush()
                current = {
                    'part_number': m.group('part').strip(),
                    'description': m.group('desc').strip(),
                    'net': _to_float(m.group('net')),
                    'amount': _to_float(m.group('amount')),
                    'qty': int(m.group('qty')),
                    'vin': None,
                    'ro_number': None,
                    'page': page_no,
                }
                continue
            if current is None:
                continue
            if RE_REPLACES.match(line):
                continue
            if current['vin'] is None:
                vm = RE_VIN.match(line)
                if vm and any(c.isalpha() for c in vm.group('vin')):
                    current['vin'] = vm.group('vin')
                continue
            rm = RE_RO.match(line)
            if rm:
                current['ro_number'] = rm.group('ro')
                flush()
                current = None
        flush()

        items.extend(_dedupe_items(page_items, sentinel_count, page_no, warnings))

    return items, warnings


def group_line_items(items):
    """Line items -> one group per (VIN, RO), in first-appearance order.

    A group with two parts is a key-with-insert: the cheaper part is the blank,
    the dearer one is the fob. Three or more parts are never guessed at.
    """
    groups = []
    index = {}
    warnings = []

    for item in items:
        key = (item['vin'], item['ro_number'])
        if key not in index:
            index[key] = {
                'vin': item['vin'],
                'ro_number': item['ro_number'],
                'key_fob_part_number': None,
                'key_fob_cost': None,
                'key_blank_part_number': None,
                'key_blank_cost': None,
                'items': [],
                'warnings': [],
                'too_many_parts': False,
            }
            groups.append(index[key])
        index[key]['items'].append(item)

    for group in groups:
        parts = group['items']
        label = f"RO {group['ro_number']} / VIN {group['vin']}"

        if any(p['qty'] > 1 for p in parts):
            group['warnings'].append(
                f"{label}: invoiced with a quantity above 1 — costs below are per part."
            )

        if len(parts) == 1:
            group['key_fob_part_number'] = parts[0]['part_number']
            group['key_fob_cost'] = parts[0]['net']
        elif len(parts) == 2:
            first, second = parts
            if first['net'] == second['net']:
                fob, blank = first, second
                group['warnings'].append(
                    f"{label}: both parts cost the same, so which one is the blank is a guess."
                )
            else:
                fob, blank = sorted(parts, key=lambda p: (p['net'] is None, p['net']), reverse=True)
            group['key_fob_part_number'] = fob['part_number']
            group['key_fob_cost'] = fob['net']
            group['key_blank_part_number'] = blank['part_number']
            group['key_blank_cost'] = blank['net']
        else:
            group['too_many_parts'] = True
            group['warnings'].append(
                f"{label}: {len(parts)} parts on one RO/VIN — too many to split into "
                f"fob and blank automatically."
            )

    warnings.extend(w for g in groups for w in g['warnings'])
    return groups, warnings


def _invoice_total(page_texts):
    """The printed TOTAL, taken off the last page. None if it can't be found."""
    if not page_texts:
        return None
    amounts = [_to_float(m) for m in RE_MONEY_TOTAL.findall(page_texts[-1])]
    amounts = [a for a in amounts if a is not None]
    return max(amounts) if amounts else None


def parse_invoice_pdf(pdf_bytes):
    """PDF bytes -> {'groups', 'line_items', 'warnings', 'parsed_total',
    'invoice_total', 'page_count'}.

    Raises ValueError when the PDF can't be opened at all; a readable PDF with
    no recognisable line items comes back with empty lists so the caller can
    say something friendlier than a traceback.
    """
    try:
        page_texts = extract_text_pages(pdf_bytes)
    except Exception as e:
        raise ValueError(f"Could not read that PDF ({e}).")

    items, warnings = parse_line_items(page_texts)
    groups, group_warnings = group_line_items(items)
    warnings = warnings + group_warnings

    parsed_total = round(sum(i['amount'] or 0 for i in items), 2)
    invoice_total = _invoice_total(page_texts)
    if items and invoice_total is not None and abs(parsed_total - invoice_total) > 0.01:
        warnings.append(
            f"Read ${parsed_total:,.2f} of parts but the invoice totals "
            f"${invoice_total:,.2f} — some lines may have been missed. "
            f"Check the list below against the paperwork before applying."
        )

    return {
        'groups': groups,
        'line_items': items,
        'warnings': warnings,
        'parsed_total': parsed_total,
        'invoice_total': invoice_total,
        'page_count': len(page_texts),
    }
