"""Parse a DMS appointments Excel export and pick out the commercial-business
rows worth adding to the fleet-prospecting call list (the cold_leads page).

Design (intentionally cheap, deterministic, and auditable — no API / NER model):

  Primary signal = the comma. The DMS exports individuals as "LASTNAME, FIRSTNAME";
  businesses are basically anything else. So comma absent => probably a business,
  comma present => probably a person.

  The keyword list is *conditioned* on that comma signal:
    - No comma  -> apply a BROAD keyword set aggressively. The missing comma
                   already implies a business, so generic business words are
                   low-risk.
    - Has comma -> apply a STRICT set: only treat it as a business if a strong
                   entity suffix (INC, LLC, CORP, ...) sits adjacent to the
                   comma. This catches "MARQUIS CONSTRUCTION SERVICES, INC" and
                   reversed exports like "CORP, APS B SAFE" while leaving a
                   person like "GLASS, ELIZABETH" (surname collides with a
                   business word) correctly classified as a person.

  This is fleet prospecting, so car dealerships are never prospects — neither the
  user's own stores nor competitors. DEALER_EXCLUDES drops them even when they
  keyword-match.

The module has no DB dependency so it can be unit-tested offline. Column layout
(0-indexed) is fixed per the export: A=store, C=lead date, L=name, M=phone.
"""

import io
import re
from datetime import datetime

import openpyxl

# Column indexes in the appointments export.
COL_STORE = 0   # A — "Fred Beans Ford of Doylestown", etc.
COL_DATE = 2    # C — lead date, "MM/DD/YYYY"
COL_NAME = 11   # L — Customer Full Name
COL_PHONE = 12  # M — Mobile Phone Number

# Strong entity suffixes. For comma names, one of these must sit next to the
# comma for the row to count as a business.
STRONG_SUFFIXES = {
    'INC', 'INCORPORATED', 'LLC', 'LLP', 'PLLC', 'CORP', 'CORPORATION',
    'CO', 'COMPANY', 'LTD', 'PC', 'LP', 'DBA',
}

# Broad business keywords applied to NO-comma names. Superset of the strong
# suffixes plus generic commercial words. Deliberately excludes auto-retail
# tells (MOTORS, AUTO SALES, dealership brands) — those are dealerships, handled
# by DEALER_EXCLUDES, not fleet prospects.
BROAD_KEYWORDS = STRONG_SUFFIXES | {
    'SERVICE', 'SERVICES', 'CONSTRUCTION', 'LANDSCAPING', 'LANDSCAPE',
    'LANDSCAPES', 'GROUP', 'TOWNSHIP', 'TWP', 'BOROUGH', 'CITY', 'COUNTY',
    'STATE', 'SUPPLY', 'EQUIPMENT', 'CONTRACTORS', 'CONTRACTING', 'CONTRACTOR',
    'MECHANICAL', 'ELECTRICAL', 'ELECTRIC', 'PLUMBING', 'REFRIGERATION',
    'MASONRY', 'DRYWALL', 'ROOFING', 'SIDING', 'PROPERTY', 'PROPERTIES',
    'REALTY', 'MANAGEMENT', 'RESCUE', 'AMBULANCE', 'POLICE', 'FIRE', 'COLLEGE',
    'ACADEMY', 'SCHOOL', 'CHURCH', 'SYSTEMS', 'SOLUTIONS', 'INDUSTRIES',
    'ENTERPRISES', 'ASSOCIATES', 'PARTNERS', 'CONCEPTS', 'VENTURE', 'HARDWOOD',
    'FLOORS', 'GLASS', 'WINDOWS', 'PAINTING', 'WALLPAPER', 'POOLS', 'WATER',
    'FUELS', 'FUEL', 'CABLE', 'METAL', 'SHEET', 'SONS', 'BROS', 'FARM',
    'CONSERVANCY', 'HEALTHCARE', 'TRANSMISSION', 'REPAIR', 'MATERIALS',
    'SECURITY', 'TRANS', 'DESIGNS', 'FLEET', 'LEASING', 'LEASE', 'TRUCK',
    'TRUCKING', 'HVAC', 'EXCAVATING', 'PAVING', 'CONCRETE', 'BUILDERS',
    'BUILDING', 'DEVELOPMENT', 'DISTRIBUTORS', 'DISTRIBUTION', 'LOGISTICS',
    'FOODS', 'FOOD', 'BAKERY', 'BREWING', 'WASTE', 'DISPOSAL', 'RECYCLING',
    'UTILITY', 'UTILITIES', 'ENVIRONMENTAL', 'ENGINEERING', 'EXTERIORS',
    'INTERIORS', 'KITCHENS', 'BATH', 'CARPETS', 'TERMINAL', 'TOWING',
}

# Auto dealerships / retail-auto outfits — never fleet prospects, dropped even
# when they keyword-match. Matched as case-insensitive substrings of the name.
DEALER_EXCLUDES = (
    'FRED BEANS', 'FAULKNER', 'ONEIL', "O'NEIL", 'SUN MOTORS', 'CARVISION',
    'CAR SENSE', 'CARSTAR', 'CHEVROLET', 'DODGE', 'CHRYSLER', 'JEEP', 'RAM ',
    'CADILLAC', 'GMC', 'BUICK', 'BMW', 'AUDI', 'LEXUS', 'INFINITI',
    'MERCEDES', 'VOLKSWAGEN', ' VW ', 'NISSAN', 'KIA', 'HONDA', 'MAZDA',
    'ACURA', 'TOYOTA', 'SUBARU', 'HYUNDAI', 'LINCOLN', 'MITSUBISHI', 'VOLVO',
    'PORSCHE', 'JAGUAR', 'AUTO SALES', 'AUTO GROUP', 'MOTORS', 'MOTORSPORTS',
    'AUTO MALL', 'AUTOMALL', 'AUTO RENT',
)

_WORD_RE = re.compile(r"[A-Za-z&.']+")
_LEADING_JUNK = "*='\" \t"


def tokens(name):
    """Uppercase word tokens, split on non-letter runs (keeping & . ')."""
    return [t.upper() for t in _WORD_RE.findall(name or '')]


def _clean_name(name):
    """Strip leading junk markers the DMS sometimes prepends (**, =, ', etc.)."""
    return (name or '').strip().lstrip(_LEADING_JUNK).strip()


def is_dealership(name):
    up = (name or '').upper()
    return any(tag in up for tag in DEALER_EXCLUDES)


def is_business(name):
    """Comma-conditioned business classifier. See module docstring."""
    n = _clean_name(name)
    if not n:
        return False
    if ',' in n:
        # Strict: a strong suffix must sit immediately beside the comma.
        parts = [p.strip() for p in n.split(',')]
        adjacent = []
        for i, part in enumerate(parts):
            tk = tokens(part)
            if not tk:
                continue
            if i > 0:           # token right after a comma
                adjacent.append(tk[0])
            if i < len(parts) - 1:   # token right before a comma
                adjacent.append(tk[-1])
        strong = {s.rstrip('.') for s in STRONG_SUFFIXES}
        return any(a.rstrip('.') in strong for a in adjacent)
    # No comma: aggressive broad keyword match.
    broad = {k.rstrip('.') for k in BROAD_KEYWORDS}
    return any(t.rstrip('.') in broad for t in tokens(n))


def extract_market(store_str, markets):
    """Map a store cell ("Fred Beans Ford of Newtown") to one of `markets` by
    case-insensitive substring match. Returns the market name or None."""
    s = (store_str or '').upper()
    for m in markets:
        if m.upper() in s:
            return m
    return None


def format_phone(raw):
    """Mirror the client formatPhone: 10 digits -> "(NNN-NNN-NNNN)", else the
    raw digits, blank -> None."""
    digits = ''.join(c for c in str(raw or '') if c.isdigit())
    if not digits:
        return None
    if len(digits) == 10:
        return f"({digits[0:3]}-{digits[3:6]}-{digits[6:]})"
    return digits


def parse_lead_date(raw):
    """"MM/DD/YYYY" -> ISO "YYYY-MM-DD". Tolerant: returns None on anything it
    can't parse."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    for fmt in ('%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def parse_appointments(file_bytes, markets):
    """Parse the appointments workbook and return business candidate dicts:
    {market, lead_date, name, phone}.

    A row is real iff its store maps to a market AND it has a name. Of those we
    keep rows where is_business() is true and is_dealership() is false. Exact
    (market, name, phone) duplicates within the file are collapsed. Returns
    (candidates, stats) where stats = {people_skipped, dealers_skipped,
    unmatched_market}.
    """
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)

    candidates = []
    seen = set()
    people_skipped = 0
    dealers_skipped = 0
    unmatched_market = 0

    for row in rows:
        if not row or len(row) <= COL_NAME:
            continue
        store = row[COL_STORE] if len(row) > COL_STORE else None
        raw_name = row[COL_NAME]
        if not raw_name or not str(raw_name).strip():
            continue
        market = extract_market(store, markets)
        if market is None:
            unmatched_market += 1
            continue
        name = _clean_name(str(raw_name))
        if not name:
            continue
        if not is_business(name):
            people_skipped += 1
            continue
        if is_dealership(name):
            dealers_skipped += 1
            continue
        phone = format_phone(row[COL_PHONE] if len(row) > COL_PHONE else None)
        lead_date = parse_lead_date(row[COL_DATE] if len(row) > COL_DATE else None)
        key = (market, name.upper(), phone or '')
        if key in seen:
            continue
        seen.add(key)
        candidates.append({
            'market': market,
            'lead_date': lead_date,
            'name': name,
            'phone': phone,
        })

    wb.close()
    stats = {
        'people_skipped': people_skipped,
        'dealers_skipped': dealers_skipped,
        'unmatched_market': unmatched_market,
    }
    return candidates, stats
